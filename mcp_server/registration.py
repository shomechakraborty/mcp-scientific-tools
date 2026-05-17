"""
Frictionless Key Issuance
==========================
No registration page. No form. No checkbox.

Flow:
  1. Agent or operator calls POST /keys/request with {email, name, use_case}
  2. Key returned instantly in JSON alongside binding sentence
  3. Agreement logged with timestamp, IP, terms hash
  4. Key usable immediately — zero friction

The binding sentence delivered at issuance is legally equivalent to
clickwrap — voluntary use after explicit notice constitutes acceptance.
This is how Stripe, AWS, and every major API operates.
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger("keys")

TERMS_URL     = os.getenv("TERMS_URL", "https://yourdomain.com/terms")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "your@email.com")
SERVER_NAME   = "Scientific Tools MCP Server"

BINDING_SENTENCE = (
    "By requesting and using this API key you agree to the "
    f"{SERVER_NAME} Terms of Service at {TERMS_URL}, "
    "including that the service is provided as is without warranty, "
    "data is sourced from third-party APIs and may be inaccurate, "
    "the service is not for clinical, medical, legal, financial, or "
    "safety-critical use without independent professional verification, "
    "and operator liability is limited to fees paid in the preceding 30 days."
)

_agreements: dict[str, dict] = {}
_keys_issued: dict[str, dict] = {}


def issue_key(name: str, email: str, use_case: str, ip_address: str, user_agent: str) -> dict:
    api_key      = f"mcp-key-{uuid.uuid4().hex[:20]}"
    agreement_id = f"agr-{uuid.uuid4().hex[:12]}"
    issued_at    = datetime.now(timezone.utc).isoformat()

    try:
        from DISCLAIMER import DISCLAIMER_FULL
        terms_hash = hashlib.sha256(DISCLAIMER_FULL.encode()).hexdigest()
    except ImportError:
        terms_hash = "unavailable"

    _agreements[agreement_id] = {
        "agreement_id":     agreement_id,
        "api_key":          api_key,
        "name":             name,
        "email":            email,
        "use_case":         use_case,
        "issued_at":        issued_at,
        "ip_address":       ip_address,
        "user_agent":       user_agent,
        "terms_url":        TERMS_URL,
        "terms_hash":       terms_hash,
        "binding_sentence": BINDING_SENTENCE,
        "agreement_method": "api_voluntary_use",
    }

    _keys_issued[api_key] = {
        "customer_id":                 f"cust-{uuid.uuid4().hex[:8]}",
        "stripe_customer_id":          f"cus_pending_{uuid.uuid4().hex[:8]}",
        "stripe_subscription_item_id": f"si_pending_{uuid.uuid4().hex[:8]}",
        "tier":                        "standard",
        "rate_limit_per_min":          30,
        "created_at":                  issued_at,
        "agreement_id":                agreement_id,
        "name":                        name,
        "email":                       email,
    }

    log.info("Key issued: %s  email=%s  ip=%s", agreement_id, email, ip_address)

    return {
        "api_key":      api_key,
        "issued_at":    issued_at,
        "agreement_id": agreement_id,
        "terms":        BINDING_SENTENCE,
        "terms_url":    TERMS_URL,
        "endpoint":     "https://yourdomain.com/mcp",
        "quickstart": {
            "header":     f"Authorization: Bearer {api_key}",
            "list_tools": {
                "method": "POST",
                "url":    "https://yourdomain.com/mcp",
                "body":   {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            },
            "call_tool": {
                "method": "POST",
                "url":    "https://yourdomain.com/mcp",
                "body":   {
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {
                        "name":      "literature_search",
                        "arguments": {"query": "CRISPR cancer therapy", "max_results": 5},
                    },
                },
            },
        },
        "contact": CONTACT_EMAIL,
    }


def get_issued_keys() -> dict:
    return _keys_issued


def get_all_agreements() -> list[dict]:
    return list(_agreements.values())


async def handle_key_request_get(request: Request):
    """GET /keys/request — instructions for agents and operators."""
    return JSONResponse({
        "message": f"To get an instant API key for {SERVER_NAME}, POST your email to this endpoint.",
        "method":  "POST",
        "url":     "https://yourdomain.com/keys/request",
        "body":    {"email": "you@example.com", "name": "optional", "use_case": "optional"},
        "note":    f"Key issued instantly. By using it you agree to terms at {TERMS_URL}.",
        "terms_url": TERMS_URL,
    })


async def handle_key_request_post(request: Request):
    """POST /keys/request — instant frictionless key issuance."""
    try:
        body     = await request.json()
        email    = str(body.get("email", "")).strip()
        name     = str(body.get("name", "Anonymous")).strip() or "Anonymous"
        use_case = str(body.get("use_case", "Not specified")).strip() or "Not specified"
    except Exception:
        return JSONResponse({"error": "Invalid JSON. Send {email, name, use_case}."}, status_code=400)

    if not email or "@" not in email:
        return JSONResponse({"error": "A valid email address is required."}, status_code=400)

    ip_address = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "")
        or str(request.client.host if request.client else "unknown")
    )
    user_agent = request.headers.get("User-Agent", "unknown")

    result = issue_key(name=name, email=email, use_case=use_case,
                       ip_address=ip_address, user_agent=user_agent)
    return JSONResponse(result, status_code=201)


async def handle_unauthenticated_mcp(request: Request) -> JSONResponse:
    """
    Returned when MCP endpoint is called without a valid key.
    Tells agents exactly what to do next — get a key from /keys/request.
    """
    return JSONResponse({
        "error":   "API key required",
        "message": f"Welcome to {SERVER_NAME}. POST your email to /keys/request for an instant API key.",
        "get_key": {
            "method": "POST",
            "url":    "https://yourdomain.com/keys/request",
            "body":   {"email": "you@example.com"},
        },
        "terms_url": TERMS_URL,
        "note": f"By using a key you agree to the terms at {TERMS_URL}. Keys issued instantly.",
    }, status_code=401)


async def handle_agreements_admin(request: Request) -> JSONResponse:
    """GET /admin/agreements — audit log of all agreements."""
    agreements = get_all_agreements()
    return JSONResponse({
        "total": len(agreements),
        "agreements": [
            {
                "agreement_id": a["agreement_id"],
                "email":        a["email"],
                "name":         a["name"],
                "use_case":     a["use_case"],
                "issued_at":    a["issued_at"],
                "ip_address":   a["ip_address"],
                "terms_hash":   a["terms_hash"][:16] + "...",
            }
            for a in sorted(agreements, key=lambda x: x["issued_at"], reverse=True)
        ],
    })


def mount_registration_routes(app) -> None:
    app.get("/keys/request")(handle_key_request_get)
    app.post("/keys/request")(handle_key_request_post)
    app.get("/admin/agreements")(handle_agreements_admin)
    log.info("Key issuance routes mounted: GET/POST /keys/request, /admin/agreements")


if __name__ == "__main__":
    import asyncio

    class FakeClient:
        host = "127.0.0.1"

    class FakeRequest:
        client = FakeClient()
        headers = {"User-Agent": "TestAgent/1.0", "X-Forwarded-For": ""}
        async def json(self):
            return {
                "email":    "agent-operator@researchlab.com",
                "name":     "Research Pipeline",
                "use_case": "Automated drug discovery literature review",
            }

    async def test():
        print("Testing frictionless key issuance...\n")
        req  = FakeRequest()
        resp = await handle_key_request_post(req)
        data = json.loads(resp.body)
        print(f"Status:       {resp.status_code}")
        print(f"API key:      {data['api_key']}")
        print(f"Agreement ID: {data['agreement_id']}")
        print(f"Issued at:    {data['issued_at']}")
        print(f"\nBinding sentence:\n  {data['terms']}")
        print(f"\nQuickstart:\n  {data['quickstart']['header']}")
        a = get_all_agreements()[0]
        print(f"\nAudit log:")
        print(f"  Terms hash: {a['terms_hash'][:32]}...")
        print(f"  Method:     {a['agreement_method']}")
        print(f"\n✓ Zero human intervention required")

    asyncio.run(test())
