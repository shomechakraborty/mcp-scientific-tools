# DISCLAIMER AND TERMS OF SERVICE
# By using this tool you agree to the terms at https://yourdomain.com/terms.
# Service provided "as is" without warranty of any kind. Data sourced from
# third-party public APIs and may be incomplete, inaccurate, or outdated.
# NOT professional medical, legal, financial, or safety advice.
# NOT for clinical, safety-critical, or regulated decision-making without
# independent professional verification.
# Operator liability limited to fees paid in the preceding 30 days.
# Users must independently verify all data before relying on it.

"""
Usage Analytics + Pricing Optimiser — Layer 7
===============================================
Tracks per-tool call volumes, latency, error rates, and revenue.
Runs a pricing optimisation loop that adjusts tool prices based on
demand elasticity — raises prices on high-demand tools, lowers on
underperforming ones to stimulate volume.

Also exposes an analytics MCP tool so agents can query usage stats.
Run standalone to see a revenue report and pricing recommendations.
"""

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("analytics")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PRICE_FLOOR = 0.001     # never price below this
PRICE_CEILING = 0.50    # never price above this
DEMAND_WINDOW_HOURS = 24
OPTIMISE_INTERVAL_HOURS = 6


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ToolStats:
    tool_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_revenue_usd: float = 0.0
    total_latency_ms: float = 0.0
    unique_customers: set = field(default_factory=set)
    hourly_calls: dict = field(default_factory=lambda: defaultdict(int))
    current_price: float = 0.0
    price_history: list = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls

    @property
    def revenue_per_call(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_revenue_usd / self.successful_calls

    def calls_in_last_n_hours(self, n: int = 24) -> int:
        now_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        total = 0
        for i in range(n):
            hour_key = (now_hour - timedelta(hours=i)).isoformat()
            total += self.hourly_calls.get(hour_key, 0)
        return total


# ---------------------------------------------------------------------------
# Analytics engine
# ---------------------------------------------------------------------------

class AnalyticsEngine:
    """
    Tracks all tool calls and runs periodic pricing optimisation.
    Integrates with the MCP server's UsageTracker.
    """

    def __init__(self):
        self._stats: dict[str, ToolStats] = {}
        self._last_optimised: float = 0.0
        self._optimisation_log: list[dict] = []

    def initialise_tool(self, tool_name: str, initial_price: float) -> None:
        if tool_name not in self._stats:
            self._stats[tool_name] = ToolStats(
                tool_name=tool_name,
                current_price=initial_price,
            )
            self._stats[tool_name].price_history.append({
                "price": initial_price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "initial",
            })

    def record_call(
        self,
        tool_name: str,
        customer_id: str,
        success: bool,
        latency_ms: float,
        revenue_usd: float,
    ) -> None:
        if tool_name not in self._stats:
            self.initialise_tool(tool_name, revenue_usd)

        stats = self._stats[tool_name]
        stats.total_calls += 1
        if success:
            stats.successful_calls += 1
            stats.total_revenue_usd += revenue_usd
            stats.total_latency_ms += latency_ms
        else:
            stats.failed_calls += 1

        stats.unique_customers.add(customer_id)

        hour_key = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ).isoformat()
        stats.hourly_calls[hour_key] += 1

        # Check if pricing optimisation should run
        if time.time() - self._last_optimised > OPTIMISE_INTERVAL_HOURS * 3600:
            self._run_pricing_optimisation()

    def _run_pricing_optimisation(self) -> list[dict]:
        """
        Pricing optimisation logic:
        1. High demand (>1000 calls/24hr) + low error rate → raise price 10%
        2. Low demand (<100 calls/24hr) + profitable → lower price 10% to stimulate volume
        3. High error rate (>10%) → lower price until fixed
        4. Price adjustments capped at ±20% per cycle
        5. Always respect floor and ceiling

        This is a simple hill-climbing optimiser. In production, replace with
        a bandit algorithm (UCB or Thompson sampling) for better convergence.
        """
        self._last_optimised = time.time()
        recommendations = []

        for tool_name, stats in self._stats.items():
            calls_24hr = stats.calls_in_last_n_hours(24)
            current_price = stats.current_price

            old_price = current_price
            reason = "no change"

            if stats.success_rate < 0.90 and stats.total_calls > 10:
                # High error rate — lower price until errors are fixed
                new_price = max(PRICE_FLOOR, current_price * 0.85)
                reason = f"high error rate {stats.success_rate:.0%}"

            elif calls_24hr > 1000 and stats.success_rate > 0.97:
                # High demand, reliable — raise price
                new_price = min(PRICE_CEILING, current_price * 1.10)
                reason = f"high demand ({calls_24hr} calls/24hr)"

            elif calls_24hr < 100 and stats.total_calls > 50:
                # Low demand — try lowering price to stimulate volume
                new_price = max(PRICE_FLOOR, current_price * 0.92)
                reason = f"low demand ({calls_24hr} calls/24hr)"

            else:
                new_price = current_price

            if abs(new_price - old_price) > 0.0001:
                stats.current_price = round(new_price, 5)
                stats.price_history.append({
                    "price": stats.current_price,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": reason,
                    "calls_24hr": calls_24hr,
                })
                log.info(
                    "Price updated: %-35s  $%.5f → $%.5f  (%s)",
                    tool_name, old_price, new_price, reason,
                )
                recommendations.append({
                    "tool": tool_name,
                    "old_price": old_price,
                    "new_price": new_price,
                    "reason": reason,
                })

        self._optimisation_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changes": recommendations,
        })
        return recommendations

    def get_optimised_price(self, tool_name: str) -> Optional[float]:
        stats = self._stats.get(tool_name)
        return stats.current_price if stats else None

    def summary_report(self) -> dict:
        now = datetime.now(timezone.utc)
        total_revenue = sum(s.total_revenue_usd for s in self._stats.values())
        total_calls = sum(s.total_calls for s in self._stats.values())
        total_customers = len(set().union(*[s.unique_customers for s in self._stats.values()]))

        tools_summary = []
        for name, stats in sorted(
            self._stats.items(), key=lambda x: x[1].total_revenue_usd, reverse=True
        ):
            tools_summary.append({
                "tool": name,
                "total_calls": stats.total_calls,
                "calls_24hr": stats.calls_in_last_n_hours(24),
                "success_rate_pct": round(stats.success_rate * 100, 1),
                "avg_latency_ms": round(stats.avg_latency_ms, 1),
                "total_revenue_usd": round(stats.total_revenue_usd, 4),
                "revenue_per_call": round(stats.revenue_per_call, 5),
                "current_price": stats.current_price,
                "unique_customers": len(stats.unique_customers),
            })

        return {
            "generated_at": now.isoformat(),
            "summary": {
                "total_revenue_usd": round(total_revenue, 4),
                "total_calls": total_calls,
                "unique_customers": total_customers,
                "tools_active": len(self._stats),
                "avg_revenue_per_call": round(total_revenue / total_calls, 6) if total_calls else 0,
            },
            "tools": tools_summary,
            "recent_price_changes": self._optimisation_log[-5:],
        }

    def revenue_projection(self, days: int = 30) -> dict:
        """Project revenue based on recent call velocity."""
        projections = {}
        for name, stats in self._stats.items():
            calls_24hr = stats.calls_in_last_n_hours(24)
            daily_revenue = calls_24hr * stats.current_price * stats.success_rate
            projections[name] = {
                "daily_calls": calls_24hr,
                "daily_revenue_usd": round(daily_revenue, 4),
                f"{days}d_revenue_usd": round(daily_revenue * days, 2),
            }

        total_daily = sum(p["daily_revenue_usd"] for p in projections.values())
        return {
            "projection_days": days,
            "total_daily_revenue_usd": round(total_daily, 4),
            f"total_{days}d_revenue_usd": round(total_daily * days, 2),
            "by_tool": projections,
        }


# ---------------------------------------------------------------------------
# Analytics MCP tool (optional — exposes stats to agents)
# ---------------------------------------------------------------------------

ANALYTICS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "report_type": {
            "type": "string",
            "enum": ["summary", "revenue_projection", "pricing"],
            "description": "Type of analytics report to return",
            "default": "summary",
        },
        "projection_days": {
            "type": "integer",
            "description": "Days to project revenue forward (for revenue_projection)",
            "default": 30,
        },
    },
}

_engine_instance: Optional[AnalyticsEngine] = None


def get_engine() -> AnalyticsEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = AnalyticsEngine()
    return _engine_instance


async def analytics_handler(arguments: dict) -> dict:
    engine = get_engine()
    report_type = arguments.get("report_type", "summary")

    if report_type == "summary":
        return engine.summary_report()
    elif report_type == "revenue_projection":
        days = int(arguments.get("projection_days", 30))
        return engine.revenue_projection(days)
    elif report_type == "pricing":
        return {
            "current_prices": {
                name: stats.current_price
                for name, stats in engine._stats.items()
            },
            "price_history": {
                name: stats.price_history[-3:]
                for name, stats in engine._stats.items()
            },
        }
    return {"error": f"Unknown report type: {report_type}"}


def register(registry) -> None:
    from server import ToolDefinition
    registry.register(ToolDefinition(
        name="analytics",
        description=(
            "Query usage analytics and revenue data for this MCP server. "
            "Returns call volumes, revenue, success rates, latency, "
            "and dynamic pricing recommendations."
        ),
        input_schema=ANALYTICS_TOOL_SCHEMA,
        price_per_call_usd=0.001,
        stripe_price_id=os.getenv("STRIPE_PRICE_ANALYTICS", "price_demo_analytics"),
        handler=analytics_handler,
        category="internal",
    ))


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import random

    engine = AnalyticsEngine()

    tools_config = {
        "literature_search":      0.020,
        "compound_lookup":        0.010,
        "gpu_spot_prices":        0.005,
        "patent_prior_art_search": 0.050,
        "scientific_data":        0.003,
    }

    for tool, price in tools_config.items():
        engine.initialise_tool(tool, price)

    # Simulate 30 days of call history
    print("Simulating 30 days of call history...")
    call_volumes = {
        "literature_search":       lambda: random.randint(800, 1200),
        "compound_lookup":         lambda: random.randint(600, 900),
        "gpu_spot_prices":         lambda: random.randint(1500, 2500),
        "patent_prior_art_search": lambda: random.randint(80, 150),
        "scientific_data":         lambda: random.randint(2000, 3500),
    }

    customers = [f"cust-{i:03d}" for i in range(20)]

    for day in range(30):
        for tool, price in tools_config.items():
            daily_calls = call_volumes[tool]()
            for _ in range(daily_calls // 24):
                engine.record_call(
                    tool_name=tool,
                    customer_id=random.choice(customers),
                    success=random.random() > 0.02,
                    latency_ms=random.uniform(80, 400),
                    revenue_usd=price,
                )

    # Print report
    report = engine.summary_report()
    print(f"\n{'═'*66}")
    print(f"MCP Tool Marketplace — Analytics Report")
    print(f"{'─'*66}")
    s = report["summary"]
    print(f"Total revenue:     ${s['total_revenue_usd']:,.2f}")
    print(f"Total calls:       {s['total_calls']:,}")
    print(f"Unique customers:  {s['unique_customers']}")
    print(f"Avg per call:      ${s['avg_revenue_per_call']:.5f}")

    print(f"\n{'─'*66}")
    print(f"{'Tool':<32} {'Calls':>8} {'Revenue':>10} {'Price':>8} {'Suc%':>6}")
    print(f"{'─'*66}")
    for t in report["tools"]:
        print(
            f"{t['tool']:<32} {t['total_calls']:>8,} "
            f"${t['total_revenue_usd']:>9,.2f} "
            f"${t['current_price']:>7.5f} "
            f"{t['success_rate_pct']:>5.1f}%"
        )

    proj = engine.revenue_projection(30)
    print(f"\n{'─'*66}")
    print(f"30-day revenue projection: ${proj['total_30d_revenue_usd']:,.2f}")
    print(f"Daily run rate:            ${proj['total_daily_revenue_usd']:,.2f}")

    changes = report.get("recent_price_changes", [])
    if changes and changes[-1].get("changes"):
        print(f"\nRecent price adjustments:")
        for c in changes[-1]["changes"]:
            direction = "↑" if c["new_price"] > c["old_price"] else "↓"
            print(f"  {direction} {c['tool']}: ${c['old_price']:.5f} → ${c['new_price']:.5f} ({c['reason']})")
