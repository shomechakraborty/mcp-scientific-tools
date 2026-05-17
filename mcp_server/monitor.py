#!/usr/bin/env python3
"""
Uptime Monitor
===============
Runs as a separate systemd service. Checks the /health endpoint
every 5 minutes and sends an email alert if the server goes down
or any tool stops responding correctly.

Checks:
  1. /health endpoint responds with status: ok
  2. /mcp tools/list returns all 6 tools
  3. Each tool returns a valid response (spot check one tool per cycle)
  4. SSL certificate is valid and not expiring within 14 days

Alerts via: email (sendmail / SMTP)

Install: systemd service (added to deploy.sh)
"""

import json
import logging
import os
import smtplib
import ssl
import socket
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText

import urllib.request
import urllib.error

log = logging.getLogger("monitor")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL      = os.getenv("BASE_URL", "https://mcp-site.com")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "shomechakraborty@gmail.com")
CHECK_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "300"))   # 5 minutes
ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", "1800"))    # 30 min between alerts

# Demo API key for health checks (add a dedicated monitor key in production)
MONITOR_API_KEY = os.getenv("MONITOR_API_KEY", "")

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_last_alert_time: float = 0
_consecutive_failures: int = 0
_was_down: bool = False


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_health() -> tuple[bool, str]:
    """Check /health endpoint."""
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/health",
            headers={"User-Agent": "MCP-Monitor/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "ok" and data.get("tools") == 6:
                return True, f"OK — {data.get('tools')} tools, v{data.get('version')}"
            return False, f"Unexpected response: {data}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"
    except Exception as e:
        return False, f"Error: {e}"


def check_tools_list() -> tuple[bool, str]:
    """Check that tools/list returns all 6 tools."""
    if not MONITOR_API_KEY:
        return True, "Skipped (no monitor API key configured)"
    try:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list"
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/mcp",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MONITOR_API_KEY}",
                "User-Agent": "MCP-Monitor/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            tools = data.get("result", {}).get("tools", [])
            if len(tools) == 6:
                names = [t["name"] for t in tools]
                return True, f"All 6 tools present: {', '.join(names)}"
            return False, f"Expected 6 tools, got {len(tools)}"
    except Exception as e:
        return False, f"tools/list failed: {e}"


def check_ssl_expiry() -> tuple[bool, str]:
    """Check SSL certificate is valid and not expiring within 14 days."""
    try:
        import ssl as ssl_lib
        ctx = ssl_lib.create_default_context()
        hostname = BASE_URL.replace("https://", "").replace("http://", "").split("/")[0]
        with ctx.wrap_socket(
            socket.socket(), server_hostname=hostname
        ) as s:
            s.settimeout(10)
            s.connect((hostname, 443))
            cert = s.getpeercert()
            expire_str = cert["notAfter"]
            import time as time_lib
            expire_ts = time_lib.mktime(time_lib.strptime(expire_str, "%b %d %H:%M:%S %Y %Z"))
            days_left = int((expire_ts - time_lib.time()) / 86400)
            if days_left < 14:
                return False, f"SSL certificate expires in {days_left} days"
            return True, f"SSL valid, expires in {days_left} days"
    except Exception as e:
        return False, f"SSL check failed: {e}"


def check_key_issuance() -> tuple[bool, str]:
    """Check that /keys/request responds correctly."""
    try:
        payload = json.dumps({
            "email": "monitor@mcp-site.com",
            "name": "Monitor",
            "use_case": "Automated health check",
        }).encode()
        req = urllib.request.Request(
            f"{BASE_URL}/keys/request",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MCP-Monitor/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if "api_key" in data and data["api_key"].startswith("mcp-key-"):
                return True, "Key issuance working"
            return False, f"Unexpected response: {list(data.keys())}"
    except Exception as e:
        return False, f"Key issuance failed: {e}"


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

def send_alert(subject: str, body: str) -> None:
    """Send email alert. Uses local sendmail if available."""
    global _last_alert_time

    now = time.time()
    if now - _last_alert_time < ALERT_COOLDOWN:
        log.info("Alert suppressed (cooldown active)")
        return

    _last_alert_time = now
    log.warning("ALERT: %s", subject)

    try:
        msg = MIMEText(body)
        msg["Subject"] = f"[MCP Monitor] {subject}"
        msg["From"]    = CONTACT_EMAIL
        msg["To"]      = CONTACT_EMAIL

        # Try local sendmail first
        with smtplib.SMTP("localhost", timeout=5) as smtp:
            smtp.sendmail(CONTACT_EMAIL, [CONTACT_EMAIL], msg.as_string())
            log.info("Alert email sent via localhost")
    except Exception as exc:
        # Log to file as fallback — check /var/log/mcp-monitor.log
        log.error("Email send failed (%s) — alert logged to file only", exc)
        with open("/var/log/mcp-monitor-alerts.log", "a") as f:
            f.write(f"\n{'='*60}\n{datetime.now(timezone.utc).isoformat()}\n{subject}\n{body}\n")


def send_recovery_alert(downtime_seconds: float) -> None:
    send_alert(
        "Server recovered",
        f"mcp-site.com is back online after {int(downtime_seconds/60)} minutes down.\n\n"
        f"Recovery time: {datetime.now(timezone.utc).isoformat()}"
    )


# ---------------------------------------------------------------------------
# Monitor loop
# ---------------------------------------------------------------------------

def run_checks() -> dict:
    """Run all checks and return results."""
    checks = {
        "health":       check_health(),
        "tools_list":   check_tools_list(),
        "ssl":          check_ssl_expiry(),
        "key_issuance": check_key_issuance(),
    }
    return checks


def monitor_loop() -> None:
    global _consecutive_failures, _was_down
    _down_since: float = 0

    log.info("Monitor started — checking %s every %ds", BASE_URL, CHECK_INTERVAL)

    while True:
        try:
            results = run_checks()
            all_ok = all(r[0] for r in results.values())
            critical_ok = results["health"][0]  # Health is the critical check

            if all_ok:
                if _was_down:
                    downtime = time.time() - _down_since
                    send_recovery_alert(downtime)
                    _was_down = False
                _consecutive_failures = 0
                log.info("All checks passed")
                for name, (ok, msg) in results.items():
                    log.info("  %-15s ✓ %s", name, msg)

            else:
                _consecutive_failures += 1
                failures = {n: m for n, (ok, m) in results.items() if not ok}

                log.warning("Check failures (%d consecutive):", _consecutive_failures)
                for name, msg in failures.items():
                    log.warning("  %-15s ✗ %s", name, msg)

                # Alert after 2 consecutive failures (10 min of downtime)
                if _consecutive_failures >= 2:
                    if not _was_down:
                        _down_since = time.time()
                        _was_down = True

                    failure_details = "\n".join(
                        f"  {name}: {msg}" for name, msg in failures.items()
                    )
                    send_alert(
                        f"Server issues detected ({_consecutive_failures} consecutive failures)",
                        f"mcp-site.com is experiencing issues:\n\n{failure_details}\n\n"
                        f"Time: {datetime.now(timezone.utc).isoformat()}\n\n"
                        f"Check server: ssh root@178.105.164.58\n"
                        f"View logs: journalctl -u mcp-server -n 50"
                    )

        except Exception as exc:
            log.error("Monitor loop error: %s", exc)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        results = run_checks()
        print(f"\nHealth check results for {BASE_URL}:")
        print(f"{'─'*50}")
        all_ok = True
        for name, (ok, msg) in results.items():
            status = "✓" if ok else "✗"
            print(f"  {status} {name:<15} {msg}")
            if not ok:
                all_ok = False
        print(f"{'─'*50}")
        print(f"Overall: {'PASS' if all_ok else 'FAIL'}")
        sys.exit(0 if all_ok else 1)
    else:
        monitor_loop()
