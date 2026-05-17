"""
MCP Server — Layer 1
=====================
Implements the Model Context Protocol (MCP) specification.
Handles agent connections, tool discovery, request routing,
API key authentication, and Stripe metered billing per call.

MCP Protocol overview:
  - Agents connect via HTTP or stdio transport
  - Server exposes: tools/list  → returns available tools + schemas
                    tools/call  → executes a tool, returns result
  - Each tool call is metered and billed via Stripe

Billing model:
  - Agent operators register with an API key (linked to a Stripe customer)
  - Each tool call is reported to Stripe as a metered usage event
  - Stripe charges the operator at end of billing period
  - You receive payouts weekly — zero capital required

Run:
  python server.py              # demo mode, no real keys needed
  python server.py --serve      # production uvicorn server
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger("mcp_server")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STRIPE_SECRET_KEY    = os.getenv("STRIPE_SECRET_KEY", "sk_test_demo")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_demo")
SERVER_VERSION       = "1.0.0"
SERVER_NAME          = "Scientific Tools MCP Server"

# Demo API keys (production: store in Redis or Postgres)
# Format: api_key -> {customer_id, stripe_customer_id, tier, rate_limit}
DEMO_API_KEYS: dict[str, dict] = {
    "mcp-key-demo-001": {
        "customer_id": "cust-research-01",
        "stripe_customer_id": "cus_demo_001",
        "stripe_subscription_item_id": "si_demo_001",
        "tier": "pro",
        "rate_limit_per_min": 60,
        "created_at": "2025-01-01T00:00:00Z",
    },
    "mcp-key-demo-002": {
        "customer_id": "cust-agent-pipeline-02",
        "stripe_customer_id": "cus_demo_002",
        "stripe_subscription_item_id": "si_demo_002",
        "tier": "standard",
        "rate_limit_per_min": 30,
        "created_at": "2025-01-01T00:00:00Z",
    },
}


# ---------------------------------------------------------------------------
# Stripe billing client
# ---------------------------------------------------------------------------

class StripeBilling:
    """
    Reports metered usage to Stripe per tool call.
    Degrades gracefully when Stripe is not configured (demo mode).
    """

    def __init__(self, secret_key: str):
        self._key = secret_key
        self._available = False
        self._stripe = None
        try:
            import stripe as _stripe
            _stripe.api_key = secret_key
            self._stripe = _stripe
            self._available = secret_key.startswith("sk_live") or secret_key.startswith("sk_test_")
            if self._available:
                log.info("Stripe billing active")
            else:
                log.info("Stripe billing in demo mode")
        except ImportError:
            log.warning("Stripe SDK not installed — billing simulated")

    def report_usage(
        self,
        subscription_item_id: str,
        quantity: int,
        timestamp: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """
        Report metered usage to Stripe.
        Called after every successful tool invocation.
        quantity=1 for standard calls, quantity=N for batch calls.
        """
        if not self._available or subscription_item_id.startswith("si_demo"):
            log.debug("Billing [DEMO]: %s × %d units", subscription_item_id, quantity)
            return {"id": f"mbur_demo_{uuid.uuid4().hex[:8]}", "quantity": quantity, "simulated": True}

        try:
            record = self._stripe.SubscriptionItem.create_usage_record(
                subscription_item_id,
                quantity=quantity,
                timestamp=timestamp or int(time.time()),
                action="increment",
                idempotency_key=idempotency_key,
            )
            return {"id": record.id, "quantity": record.quantity}
        except Exception as exc:
            log.error("Stripe usage report failed: %s", exc)
            return {"id": "billing_error", "error": str(exc)}

    def create_customer(self, email: str, name: str) -> Optional[str]:
        """Create a Stripe customer. Returns customer ID."""
        if not self._available:
            return f"cus_demo_{uuid.uuid4().hex[:8]}"
        try:
            customer = self._stripe.Customer.create(email=email, name=name)
            return customer.id
        except Exception as exc:
            log.error("Stripe customer creation failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """Defines one tool exposed by this MCP server."""
    name: str
    description: str
    input_schema: dict
    price_per_call_usd: float
    stripe_price_id: str           # Stripe metered price ID for this tool
    handler: Any = field(default=None, repr=False)
    category: str = "general"
    version: str = "1.0.0"

    def to_mcp_schema(self) -> dict:
        """Returns MCP-compatible tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class ToolRegistry:
    """Manages all registered tools."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        log.info("Registered tool: %s ($%.4f/call)", tool.name, tool.price_per_call_usd)

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def count(self) -> int:
        return len(self._tools)


# ---------------------------------------------------------------------------
# Usage tracker (in-memory; production: Redis + Postgres)
# ---------------------------------------------------------------------------

@dataclass
class CallRecord:
    call_id: str
    customer_id: str
    tool_name: str
    price_usd: float
    duration_ms: float
    success: bool
    error: Optional[str]
    stripe_record_id: Optional[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UsageTracker:
    def __init__(self):
        self._calls: list[CallRecord] = []
        self._rate_windows: dict[str, list[float]] = {}  # api_key -> [timestamps]

    def record(self, record: CallRecord) -> None:
        self._calls.append(record)

    def check_rate_limit(self, api_key: str, limit_per_min: int) -> bool:
        """Returns True if within rate limit, False if exceeded."""
        now = time.time()
        window = self._rate_windows.get(api_key, [])
        window = [t for t in window if now - t < 60]
        if len(window) >= limit_per_min:
            return False
        window.append(now)
        self._rate_windows[api_key] = window
        return True

    def summary(self) -> dict:
        total = len(self._calls)
        successful = sum(1 for c in self._calls if c.success)
        total_revenue = sum(c.price_usd for c in self._calls if c.success)
        by_tool: dict[str, int] = {}
        for c in self._calls:
            by_tool[c.tool_name] = by_tool.get(c.tool_name, 0) + 1
        return {
            "total_calls": total,
            "successful_calls": successful,
            "failed_calls": total - successful,
            "total_revenue_usd": round(total_revenue, 6),
            "calls_by_tool": by_tool,
            "avg_revenue_per_call": round(total_revenue / successful, 6) if successful else 0,
        }


# ---------------------------------------------------------------------------
# MCP request / response models
# ---------------------------------------------------------------------------

class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Any
    method: str
    params: Optional[dict] = None


class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Any
    result: Optional[Any] = None
    error: Optional[dict] = None


class ToolCallParams(BaseModel):
    name: str
    arguments: Optional[dict] = {}


# ---------------------------------------------------------------------------
# MCP Server app
# ---------------------------------------------------------------------------

registry = ToolRegistry()
billing  = StripeBilling(STRIPE_SECRET_KEY)
tracker  = UsageTracker()


def _authenticate(authorization: Optional[str]) -> dict:
    """
    Validate API key. On missing/invalid key, raises HTTPException with
    onboarding instructions rather than a bare 401 error.
    Agents hitting this know exactly how to get a key.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "error":   "API key required",
                "message": f"Welcome to {SERVER_NAME}. POST your email to /keys/request for an instant API key.",
                "get_key": {
                    "method": "POST",
                    "url":    "https://yourdomain.com/keys/request",
                    "body":   {"email": "you@example.com"},
                },
                "terms_url": "https://yourdomain.com/terms",
                "note": "By using a key you agree to the terms. Keys issued instantly.",
            }
        )

    key = authorization[7:].strip()
    customer = DEMO_API_KEYS.get(key)

    if not customer:
        try:
            from registration import get_issued_keys
            customer = get_issued_keys().get(key)
        except ImportError:
            pass

    if not customer:
        raise HTTPException(
            status_code=401,
            detail={
                "error":   "Invalid API key",
                "message": "This key was not found. Get a new key at /keys/request.",
                "get_key": "POST https://yourdomain.com/keys/request",
            }
        )
    return {**customer, "api_key": key}


async def _execute_tool(tool: ToolDefinition, arguments: dict, customer: dict) -> tuple[Any, float]:
    """Execute a tool handler and return (result, duration_ms)."""
    t0 = time.monotonic()
    if asyncio.iscoroutinefunction(tool.handler):
        result = await tool.handler(arguments)
    else:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: tool.handler(arguments)
        )
    duration_ms = (time.monotonic() - t0) * 1000
    return result, duration_ms


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("MCP server starting — %d tools registered", registry.count())
    yield
    log.info("MCP server stopped. Stats: %s", tracker.summary())


app = FastAPI(
    title=SERVER_NAME,
    version=SERVER_VERSION,
    description="MCP-compatible server providing scientific tools for AI agents.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# MCP Protocol endpoints
# ---------------------------------------------------------------------------

@app.post("/mcp")
async def mcp_endpoint(request: MCPRequest, authorization: str = Header(None)):
    """Main MCP JSON-RPC endpoint."""
    customer = _authenticate(authorization)

    # Rate limit check
    rate_limit = customer.get("rate_limit_per_min", 30)
    if not tracker.check_rate_limit(customer["api_key"], rate_limit):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "limit": rate_limit, "window": "60s"}
        )

    method = request.method

    # --- tools/list: return all available tools ---
    if method == "tools/list":
        tools_schema = [t.to_mcp_schema() for t in registry.list_all()]
        return MCPResponse(
            id=request.id,
            result={
                "tools": tools_schema,
                "server": SERVER_NAME,
                "version": SERVER_VERSION,
                "disclaimer": (
                    "BY USING THIS SERVICE YOU AGREE TO THE TERMS AT "
                    "https://yourdomain.com/terms. "
                    "Service provided as is without warranty. "
                    "Data sourced from third-party APIs and may be inaccurate. "
                    "Not for clinical, legal, financial, or safety-critical use. "
                    "Not professional medical, legal, or financial advice. "
                    "Operator liability limited to fees paid in preceding 30 days. "
                    "Users must independently verify all data before relying on it."
                ),
            }
        )

    # --- tools/call: execute a specific tool ---
    if method == "tools/call":
        params = request.params or {}
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            return MCPResponse(
                id=request.id,
                error={"code": -32602, "message": "Missing tool name"}
            )

        tool = registry.get(tool_name)
        if not tool:
            return MCPResponse(
                id=request.id,
                error={"code": -32601, "message": f"Tool not found: {tool_name}"}
            )

        call_id = f"call-{uuid.uuid4().hex[:12]}"
        try:
            result, duration_ms = await _execute_tool(tool, arguments, customer)
            success = True
            error_msg = None
        except Exception as exc:
            log.error("Tool %s failed for %s: %s", tool_name, customer["customer_id"], exc)
            result = None
            duration_ms = 0
            success = False
            error_msg = str(exc)

        # Report to Stripe (only on success)
        stripe_record_id = None
        if success:
            idempotency_key = hashlib.sha256(call_id.encode()).hexdigest()
            billing_result = billing.report_usage(
                subscription_item_id=customer["stripe_subscription_item_id"],
                quantity=1,
                idempotency_key=idempotency_key,
            )
            stripe_record_id = billing_result.get("id")

        # Record in tracker
        tracker.record(CallRecord(
            call_id=call_id,
            customer_id=customer["customer_id"],
            tool_name=tool_name,
            price_usd=tool.price_per_call_usd if success else 0,
            duration_ms=round(duration_ms, 2),
            success=success,
            error=error_msg,
            stripe_record_id=stripe_record_id,
        ))

        log.info(
            "Tool %-32s  customer=%-20s  %s  %.0fms  $%.4f",
            tool_name, customer["customer_id"],
            "OK" if success else "ERR",
            duration_ms, tool.price_per_call_usd if success else 0,
        )

        if not success:
            return MCPResponse(
                id=request.id,
                error={"code": -32603, "message": f"Tool execution failed: {error_msg}"}
            )

        return MCPResponse(
            id=request.id,
            result={
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False,
                "_meta": {
                    "call_id": call_id,
                    "duration_ms": round(duration_ms, 2),
                    "billed": True,
                }
            }
        )

    # --- initialize: MCP handshake ---
    if method == "initialize":
        return MCPResponse(
            id=request.id,
            result={
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        )

    # --- Unknown method ---
    return MCPResponse(
        id=request.id,
        error={"code": -32601, "message": f"Method not found: {method}"}
    )


@app.get("/terms")
def terms():
    """Returns the full terms of service and legal disclaimer as plain text."""
    try:
        from DISCLAIMER import DISCLAIMER_FULL
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(DISCLAIMER_FULL)
    except ImportError:
        return {"error": "Terms not found"}





@app.get("/health")
def health():
    return {
        "status": "ok",
        "tools": registry.count(),
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/stats")
def stats(authorization: str = Header(None)):
    _authenticate(authorization)
    return tracker.summary()


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    log.info("Stripe webhook received")
    return {"received": True}


# ---------------------------------------------------------------------------
# Demo harness
# ---------------------------------------------------------------------------

def _demo():
    """Run a demo without starting uvicorn."""
    import asyncio

    async def run():
        print(f"\n{'═'*64}")
        print(f"MCP Server — Demo")
        print(f"{'─'*64}\n")

        # Show registered tools
        print(f"Registered tools: {registry.count()}")
        for t in registry.list_all():
            print(f"  {t.name:<40} ${t.price_per_call_usd:.4f}/call")

        # Simulate tool list request
        req = MCPRequest(id=1, method="tools/list", jsonrpc="2.0")
        resp = await mcp_endpoint(req, authorization="Bearer mcp-key-demo-001")
        tools_returned = len(resp.result.get("tools", []))
        print(f"\ntools/list → {tools_returned} tools returned")

        # Simulate tool calls
        print(f"\n{'─'*64}")
        print("Simulating tool calls:\n")

        test_calls = [
            ("literature_search", {"query": "CRISPR gene editing cancer therapy", "max_results": 3}),
            ("compound_lookup",   {"identifier": "aspirin", "id_type": "name"}),
            ("gpu_spot_prices",   {"gpu_type": "a100_80gb"}),
        ]

        for tool_name, args in test_calls:
            tool = registry.get(tool_name)
            if not tool:
                print(f"  {tool_name}: not yet registered")
                continue
            req = MCPRequest(
                id=uuid.uuid4().hex[:8],
                method="tools/call",
                jsonrpc="2.0",
                params={"name": tool_name, "arguments": args}
            )
            resp = await mcp_endpoint(req, authorization="Bearer mcp-key-demo-001")
            if resp.result:
                meta = resp.result.get("_meta", {})
                print(f"  {tool_name:<35} OK  {meta.get('duration_ms', 0):.0f}ms  billed={meta.get('billed', False)}")
            else:
                print(f"  {tool_name:<35} ERR {resp.error}")

        # Usage summary
        print(f"\n{'═'*64}")
        s = tracker.summary()
        print(f"Calls:    {s['total_calls']} total / {s['successful_calls']} successful")
        print(f"Revenue:  ${s['total_revenue_usd']:.4f}")
        print(f"By tool:  {s['calls_by_tool']}")

    asyncio.run(run())


if __name__ == "__main__":
    import sys
    # Import tools so they register themselves
    try:
        from tools.literature_search import register as reg_lit
        reg_lit(registry)
    except ImportError:
        pass
    try:
        from tools.compound_lookup import register as reg_chem
        reg_chem(registry)
    except ImportError:
        pass
    try:
        from tools.gpu_spot_prices import register as reg_gpu
        reg_gpu(registry)
    except ImportError:
        pass

    if "--serve" in sys.argv:
        uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
    else:
        _demo()
