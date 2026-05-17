"""
Persistent Storage — Layer 8
==============================
SQLite-backed persistence for:
  - Issued API keys (survive server restarts)
  - Agreement audit log (permanent legal record)
  - Call log (revenue reconciliation)
  - Tool health status (response validation)

Uses SQLAlchemy with SQLite for zero-config deployment.
Production upgrade path: swap SQLite URL for Postgres URL — no code changes needed.

Database file: /opt/mcp-server/data/mcp.db
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("db")

DB_PATH = os.getenv("DB_PATH", "/opt/mcp-server/data/mcp.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

try:
    from sqlalchemy import (
        create_engine, Column, String, Float, Boolean,
        Integer, Text, DateTime, Index, text
    )
    from sqlalchemy.orm import declarative_base, sessionmaker, Session
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    log.warning("SQLAlchemy not available — using in-memory fallback")

if SQLALCHEMY_AVAILABLE:
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base = declarative_base()

    class APIKey(Base):
        __tablename__ = "api_keys"
        api_key                      = Column(String, primary_key=True)
        customer_id                  = Column(String, nullable=False)
        stripe_customer_id           = Column(String)
        stripe_subscription_item_id  = Column(String)
        tier                         = Column(String, default="standard")
        rate_limit_per_min           = Column(Integer, default=30)
        name                         = Column(String)
        email                        = Column(String)
        agreement_id                 = Column(String)
        created_at                   = Column(String)
        active                       = Column(Boolean, default=True)

    class Agreement(Base):
        __tablename__ = "agreements"
        agreement_id      = Column(String, primary_key=True)
        api_key           = Column(String)
        name              = Column(String)
        email             = Column(String)
        use_case          = Column(Text)
        issued_at         = Column(String)
        ip_address        = Column(String)
        user_agent        = Column(String)
        terms_url         = Column(String)
        terms_hash        = Column(String)
        binding_sentence  = Column(Text)
        agreement_method  = Column(String)

    class CallLog(Base):
        __tablename__ = "call_logs"
        id           = Column(Integer, primary_key=True, autoincrement=True)
        call_id      = Column(String, unique=True)
        customer_id  = Column(String)
        tool_name    = Column(String)
        price_usd    = Column(Float)
        duration_ms  = Column(Float)
        success      = Column(Boolean)
        error        = Column(Text)
        stripe_id    = Column(String)
        timestamp    = Column(String)
        __table_args__ = (
            Index("ix_call_logs_customer", "customer_id"),
            Index("ix_call_logs_tool", "tool_name"),
            Index("ix_call_logs_timestamp", "timestamp"),
        )

    class ToolHealth(Base):
        __tablename__ = "tool_health"
        tool_name       = Column(String, primary_key=True)
        last_success_at = Column(String)
        last_error_at   = Column(String)
        last_error_msg  = Column(Text)
        success_count   = Column(Integer, default=0)
        error_count     = Column(Integer, default=0)
        avg_latency_ms  = Column(Float, default=0.0)

    Base.metadata.create_all(engine)
    log.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def save_key(key_data: dict) -> None:
    if not SQLALCHEMY_AVAILABLE:
        return
    with SessionLocal() as db:
        existing = db.get(APIKey, key_data["api_key"])
        if not existing:
            db.add(APIKey(**{
                k: v for k, v in key_data.items()
                if k in APIKey.__table__.columns.keys()
            }))
            db.commit()


def load_key(api_key: str) -> Optional[dict]:
    if not SQLALCHEMY_AVAILABLE:
        return None
    with SessionLocal() as db:
        row = db.get(APIKey, api_key)
        if row and row.active:
            return {
                "customer_id":                 row.customer_id,
                "stripe_customer_id":          row.stripe_customer_id,
                "stripe_subscription_item_id": row.stripe_subscription_item_id,
                "tier":                        row.tier,
                "rate_limit_per_min":          row.rate_limit_per_min,
                "created_at":                  row.created_at,
                "agreement_id":                row.agreement_id,
                "name":                        row.name,
                "email":                       row.email,
            }
    return None


def load_all_keys() -> dict:
    """Load all active keys — used to populate in-memory cache on startup."""
    if not SQLALCHEMY_AVAILABLE:
        return {}
    with SessionLocal() as db:
        rows = db.query(APIKey).filter(APIKey.active == True).all()
        return {
            row.api_key: {
                "customer_id":                 row.customer_id,
                "stripe_customer_id":          row.stripe_customer_id,
                "stripe_subscription_item_id": row.stripe_subscription_item_id,
                "tier":                        row.tier,
                "rate_limit_per_min":          row.rate_limit_per_min,
                "created_at":                  row.created_at,
                "agreement_id":                row.agreement_id,
                "name":                        row.name,
                "email":                       row.email,
            }
            for row in rows
        }


def save_agreement(agreement_data: dict) -> None:
    if not SQLALCHEMY_AVAILABLE:
        return
    with SessionLocal() as db:
        db.add(Agreement(**{
            k: v for k, v in agreement_data.items()
            if k in Agreement.__table__.columns.keys()
        }))
        db.commit()


def load_all_agreements() -> list[dict]:
    if not SQLALCHEMY_AVAILABLE:
        return []
    with SessionLocal() as db:
        rows = db.query(Agreement).order_by(Agreement.issued_at.desc()).all()
        return [
            {c.name: getattr(row, c.name) for c in Agreement.__table__.columns}
            for row in rows
        ]


def save_call(call_data: dict) -> None:
    if not SQLALCHEMY_AVAILABLE:
        return
    with SessionLocal() as db:
        db.add(CallLog(**{
            k: v for k, v in call_data.items()
            if k in CallLog.__table__.columns.keys()
        }))
        db.commit()


def update_tool_health(tool_name: str, success: bool, latency_ms: float, error: str = "") -> None:
    if not SQLALCHEMY_AVAILABLE:
        return
    with SessionLocal() as db:
        row = db.get(ToolHealth, tool_name)
        if not row:
            row = ToolHealth(tool_name=tool_name)
            db.add(row)
        now = datetime.now(timezone.utc).isoformat()
        if success:
            row.last_success_at = now
            row.success_count = (row.success_count or 0) + 1
            prev_avg = row.avg_latency_ms or 0
            total = row.success_count
            row.avg_latency_ms = round(
                (prev_avg * (total - 1) + latency_ms) / total, 2
            )
        else:
            row.last_error_at = now
            row.last_error_msg = error[:500]
            row.error_count = (row.error_count or 0) + 1
        db.commit()


def get_tool_health() -> list[dict]:
    if not SQLALCHEMY_AVAILABLE:
        return []
    with SessionLocal() as db:
        rows = db.query(ToolHealth).all()
        return [
            {c.name: getattr(row, c.name) for c in ToolHealth.__table__.columns}
            for row in rows
        ]


def get_revenue_summary() -> dict:
    """Aggregate revenue stats from call log."""
    if not SQLALCHEMY_AVAILABLE:
        return {}
    with SessionLocal() as db:
        from sqlalchemy import func
        total = db.query(
            func.count(CallLog.id),
            func.sum(CallLog.price_usd),
        ).filter(CallLog.success == True).first()

        by_tool = db.query(
            CallLog.tool_name,
            func.count(CallLog.id),
            func.sum(CallLog.price_usd),
        ).filter(CallLog.success == True).group_by(CallLog.tool_name).all()

        return {
            "total_calls":       total[0] or 0,
            "total_revenue_usd": round(float(total[1] or 0), 4),
            "by_tool": {
                row[0]: {
                    "calls":   row[1],
                    "revenue": round(float(row[2] or 0), 4),
                }
                for row in by_tool
            },
        }


if __name__ == "__main__":
    print(f"Database: {DB_PATH}")
    print(f"SQLAlchemy available: {SQLALCHEMY_AVAILABLE}")
    if SQLALCHEMY_AVAILABLE:
        keys = load_all_keys()
        agreements = load_all_agreements()
        health = get_tool_health()
        revenue = get_revenue_summary()
        print(f"Keys loaded: {len(keys)}")
        print(f"Agreements: {len(agreements)}")
        print(f"Tool health records: {len(health)}")
        print(f"Revenue summary: {revenue}")
        print("✓ Database operational")
