"""
Billing System
===============
Complete Stripe billing integration:

  GET  /                    Landing page with pricing and Get API Key button
  GET  /pricing             Pricing page
  POST /billing/checkout    Create Stripe checkout session → redirect to Stripe
  GET  /billing/success     Post-checkout success → activate key, show it
  GET  /billing/cancel      Checkout cancelled → back to landing
  POST /webhooks/stripe     Handle payment events (subscription created, failed)

Flow:
  1. Operator visits mcp-site.com
  2. Clicks "Get API Key"
  3. Enters email → POST /billing/checkout
  4. Redirected to Stripe hosted checkout
  5. Adds card, completes checkout
  6. Redirected to /billing/success
  7. Key displayed — immediately active
  8. Stripe bills monthly based on metered usage

Free tier:
  First 100 calls free. After that, metered billing kicks in.
  This gives operators a chance to evaluate before being charged.
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

log = logging.getLogger("billing")

STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
DOMAIN                = os.getenv("TERMS_URL", "https://mcp-site.com").replace("/terms", "")
CONTACT_EMAIL         = os.getenv("CONTACT_EMAIL", "shomechakraborty@gmail.com")

# Stripe price IDs for each tool
STRIPE_PRICES = {
    "literature_search":       os.getenv("STRIPE_PRICE_LITERATURE", ""),
    "compound_lookup":         os.getenv("STRIPE_PRICE_COMPOUND", ""),
    "gpu_spot_prices":         os.getenv("STRIPE_PRICE_GPU", ""),
    "patent_prior_art_search": os.getenv("STRIPE_PRICE_PATENT", ""),
    "scientific_data":         os.getenv("STRIPE_PRICE_SCIDATA", ""),
    "analytics":               os.getenv("STRIPE_PRICE_ANALYTICS", ""),
}

FREE_CALL_LIMIT = 100

# Pending checkouts: session_id -> {email, name, use_case, pending_key}
_pending_checkouts: dict[str, dict] = {}

# Active subscriptions: customer_id -> {subscription_id, items}
_active_subscriptions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Stripe client
# ---------------------------------------------------------------------------

def get_stripe():
    try:
        import stripe as _stripe
        _stripe.api_key = STRIPE_SECRET_KEY
        return _stripe
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Scientific Tools MCP Server</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#0a0a0a;color:#e8e8e8;line-height:1.6}}
    .hero{{max-width:800px;margin:0 auto;padding:4rem 2rem 2rem}}
    h1{{font-size:2.2rem;font-weight:700;margin-bottom:1rem;color:#fff}}
    .sub{{font-size:1.1rem;color:#888;margin-bottom:2.5rem;max-width:560px}}
    .tools{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
            gap:12px;margin-bottom:3rem}}
    .tool{{background:#141414;border:1px solid #222;border-radius:10px;
           padding:1rem 1.2rem}}
    .tool-name{{font-size:.95rem;font-weight:500;color:#fff;margin-bottom:4px}}
    .tool-desc{{font-size:.82rem;color:#666;margin-bottom:8px}}
    .tool-price{{font-size:.82rem;font-weight:500;color:#4ade80}}
    .cta-section{{background:#141414;border:1px solid #222;border-radius:12px;
                  padding:2rem;margin-bottom:2rem}}
    .cta-title{{font-size:1.2rem;font-weight:600;color:#fff;margin-bottom:.5rem}}
    .cta-sub{{font-size:.9rem;color:#666;margin-bottom:1.5rem}}
    .form-row{{display:flex;gap:10px;flex-wrap:wrap}}
    input{{flex:1;min-width:200px;padding:.7rem 1rem;background:#0a0a0a;
           border:1px solid #333;border-radius:8px;color:#fff;font-size:.95rem}}
    input:focus{{outline:none;border-color:#555}}
    input::placeholder{{color:#444}}
    .btn{{padding:.7rem 1.8rem;background:#fff;color:#000;border:none;
          border-radius:8px;font-size:.95rem;font-weight:600;cursor:pointer;
          white-space:nowrap;transition:background .15s}}
    .btn:hover{{background:#e8e8e8}}
    .free-note{{font-size:.8rem;color:#555;margin-top:.75rem}}
    .divider{{border:none;border-top:1px solid #1a1a1a;margin:2rem 0}}
    .footer{{max-width:800px;margin:0 auto;padding:1rem 2rem 3rem;
             display:flex;gap:1.5rem;flex-wrap:wrap}}
    .footer a{{font-size:.82rem;color:#444;text-decoration:none}}
    .footer a:hover{{color:#888}}
    .badge{{display:inline-block;font-size:.72rem;padding:2px 8px;
            border-radius:20px;background:#1a2a1a;color:#4ade80;
            border:1px solid #2a3a2a;margin-bottom:1rem}}
    code{{background:#1a1a1a;padding:.15rem .4rem;border-radius:4px;
          font-size:.82rem;color:#888}}
  </style>
</head>
<body>
<div class="hero">
  <div class="badge">● Live — 6 tools available</div>
  <h1>Scientific Tools<br>MCP Server</h1>
  <p class="sub">High-value scientific data tools for AI agents.
  Plug into any MCP-compatible agent pipeline. Pay per call.</p>

  <div class="tools">
    <div class="tool">
      <div class="tool-name">Literature Search</div>
      <div class="tool-desc">PubMed, arXiv, Semantic Scholar</div>
      <div class="tool-price">$0.020 / call</div>
    </div>
    <div class="tool">
      <div class="tool-name">Compound Lookup</div>
      <div class="tool-desc">PubChem, ChEMBL molecular data</div>
      <div class="tool-price">$0.010 / call</div>
    </div>
    <div class="tool">
      <div class="tool-name">Patent Prior Art</div>
      <div class="tool-desc">USPTO and EPO databases</div>
      <div class="tool-price">$0.050 / call</div>
    </div>
    <div class="tool">
      <div class="tool-name">GPU Spot Prices</div>
      <div class="tool-desc">AWS, CoreWeave, Lambda, Vast</div>
      <div class="tool-price">$0.005 / call</div>
    </div>
    <div class="tool">
      <div class="tool-name">Scientific Data</div>
      <div class="tool-desc">USGS, NASA, OpenAQ</div>
      <div class="tool-price">$0.003 / call</div>
    </div>
    <div class="tool">
      <div class="tool-name">Analytics</div>
      <div class="tool-desc">Usage and revenue reporting</div>
      <div class="tool-price">$0.001 / call</div>
    </div>
  </div>

  <div class="cta-section">
    <div class="cta-title">Get your API key</div>
    <div class="cta-sub">First 100 calls free. Then pay only for what you use, billed monthly.</div>
    <form action="/billing/checkout" method="POST">
      <div class="form-row">
        <input type="email" name="email" placeholder="your@email.com" required>
        <input type="text" name="name" placeholder="Your name (optional)">
        <button type="submit" class="btn">Get API Key →</button>
      </div>
      <p class="free-note">
        By continuing you agree to our
        <a href="/terms" style="color:#555">Terms of Service</a> and
        <a href="/privacy" style="color:#555">Privacy Policy</a>.
        A payment method is required after your free tier is used.
      </p>
    </form>
  </div>

  <hr class="divider">

  <div style="margin-bottom:1.5rem">
    <div style="font-size:.9rem;color:#666;margin-bottom:.75rem">
      Connect your agent in seconds:
    </div>
    <code style="display:block;padding:1rem;background:#0f0f0f;
                 border:1px solid #1a1a1a;border-radius:8px;
                 font-size:.82rem;color:#888;line-height:1.8">
      &#123; "mcpServers": &#123; "scientific-tools": &#123;<br>
      &nbsp;&nbsp;"url": "https://mcp-site.com/mcp",<br>
      &nbsp;&nbsp;"headers": &#123; "Authorization": "Bearer YOUR_KEY" &#125;<br>
      &#125; &#125; &#125;
    </code>
  </div>

</div>

<div class="footer">
  <a href="/terms">Terms of Service</a>
  <a href="/privacy">Privacy Policy</a>
  <a href="mailto:{contact}">{contact}</a>
  <a href="https://github.com/shomechakraborty/mcp-scientific-tools">GitHub</a>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Checkout flow
# ---------------------------------------------------------------------------

async def handle_landing(request: Request) -> HTMLResponse:
    """GET / — serve landing page."""
    return HTMLResponse(LANDING_PAGE.replace("{contact}", CONTACT_EMAIL))


async def handle_checkout_post(request: Request):
    """
    POST /billing/checkout
    Create a Stripe checkout session and redirect operator to Stripe.
    """
    form     = await request.form()
    email    = str(form.get("email", "")).strip()
    name     = str(form.get("name", "")).strip() or "Anonymous"
    use_case = str(form.get("use_case", "")).strip() or "Not specified"

    if not email or "@" not in email:
        return HTMLResponse("<p>Invalid email. <a href='/'>Go back</a></p>", status_code=400)

    stripe = get_stripe()
    if not stripe or not STRIPE_SECRET_KEY or STRIPE_SECRET_KEY == "sk_test_demo":
        # Demo mode — issue key directly without payment
        from registration import issue_key
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or str(request.client.host)
        ua = request.headers.get("User-Agent", "unknown")
        result = issue_key(name=name, email=email, use_case=use_case, ip_address=ip, user_agent=ua)
        return HTMLResponse(_success_page(name, result["api_key"], result["agreement_id"], demo=True))

    try:
        # Create Stripe customer
        customer = stripe.Customer.create(email=email, name=name)
        customer_id = customer.id

        # Generate pending key
        pending_key  = f"mcp-key-{uuid.uuid4().hex[:20]}"
        session_id_placeholder = f"sess_{uuid.uuid4().hex[:16]}"

        # Build line items — one per tool (metered)
        line_items = []
        for tool_name, price_id in STRIPE_PRICES.items():
            if price_id:
                line_items.append({
                    "price": price_id,
                    "quantity": 0,   # metered — starts at 0
                })

        if not line_items:
            # Fallback — no prices configured, issue key in demo mode
            from registration import issue_key
            ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or str(request.client.host)
            ua = request.headers.get("User-Agent", "unknown")
            result = issue_key(name=name, email=email, use_case=use_case, ip_address=ip, user_agent=ua)
            return HTMLResponse(_success_page(name, result["api_key"], result["agreement_id"], demo=True))

        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            mode="subscription",
            line_items=line_items,
            success_url=f"{DOMAIN}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/billing/cancel",
            metadata={
                "email":       email,
                "name":        name,
                "use_case":    use_case,
                "pending_key": pending_key,
            },
            subscription_data={
                "metadata": {
                    "email":       email,
                    "pending_key": pending_key,
                }
            },
        )

        # Store pending checkout
        _pending_checkouts[session.id] = {
            "email":       email,
            "name":        name,
            "use_case":    use_case,
            "pending_key": pending_key,
            "customer_id": customer_id,
        }

        return RedirectResponse(session.url, status_code=303)

    except Exception as exc:
        log.error("Checkout creation failed: %s", exc)
        return HTMLResponse(
            f"<p>Error creating checkout: {exc}. <a href='/'>Go back</a></p>",
            status_code=500,
        )


async def handle_billing_success(request: Request) -> HTMLResponse:
    """
    GET /billing/success?session_id=...
    Called after successful Stripe checkout.
    Activates the pending key and displays it.
    """
    session_id = request.query_params.get("session_id", "")

    stripe = get_stripe()
    if not stripe or not session_id:
        return HTMLResponse("<p>Invalid session. <a href='/'>Go back</a></p>", status_code=400)

    try:
        session  = stripe.checkout.Session.retrieve(session_id)
        metadata = session.metadata or {}
        email       = metadata.get("email", "")
        name        = metadata.get("name", "Anonymous")
        use_case    = metadata.get("use_case", "Not specified")
        pending_key = metadata.get("pending_key", "")
        customer_id = session.customer

        if not pending_key:
            pending_checkout = _pending_checkouts.get(session_id, {})
            pending_key = pending_checkout.get("pending_key", f"mcp-key-{uuid.uuid4().hex[:20]}")
            email = email or pending_checkout.get("email", "")
            name  = name  or pending_checkout.get("name", "Anonymous")

        # Get subscription details for usage reporting
        subscription_id = session.subscription
        subscription_items = {}
        if subscription_id:
            sub = stripe.Subscription.retrieve(subscription_id)
            for item in sub["items"]["data"]:
                price_id = item["price"]["id"]
                # Map price ID back to tool name
                for tool, pid in STRIPE_PRICES.items():
                    if pid == price_id:
                        subscription_items[tool] = item["id"]
            _active_subscriptions[customer_id] = {
                "subscription_id": subscription_id,
                "items": subscription_items,
            }

        # Issue and activate the key
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or str(request.client.host)
        ua = request.headers.get("User-Agent", "unknown")

        from registration import issue_key, _keys_issued
        result = issue_key(
            name=name, email=email, use_case=use_case,
            ip_address=ip, user_agent=ua,
        )
        api_key = result["api_key"]

        # Update key with real Stripe IDs
        if api_key in _keys_issued:
            _keys_issued[api_key]["stripe_customer_id"] = customer_id
            if subscription_items:
                first_item = list(subscription_items.values())[0]
                _keys_issued[api_key]["stripe_subscription_item_id"] = first_item
                _keys_issued[api_key]["subscription_items"] = subscription_items

        # Persist updated key
        from db import save_key
        save_key({"api_key": api_key, **_keys_issued[api_key]})

        # Clean up pending checkout
        _pending_checkouts.pop(session_id, None)

        log.info("Key activated after checkout: %s email=%s", api_key[:24], email)
        return HTMLResponse(_success_page(name, api_key, result["agreement_id"]))

    except Exception as exc:
        log.error("Billing success handler failed: %s", exc)
        return HTMLResponse(
            f"<p>Error activating key: {exc}. Contact {CONTACT_EMAIL}</p>",
            status_code=500,
        )


async def handle_billing_cancel(request: Request) -> HTMLResponse:
    """GET /billing/cancel — operator cancelled checkout."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Cancelled</title>
<style>body{{font-family:sans-serif;background:#0a0a0a;color:#888;
display:flex;align-items:center;justify-content:center;height:100vh;text-align:center}}</style>
</head><body>
<div>
  <p style="font-size:1.1rem;margin-bottom:1rem">Checkout cancelled.</p>
  <a href="/" style="color:#fff">← Back to home</a>
</div>
</body></html>""")


# ---------------------------------------------------------------------------
# Webhook handler — subscription events
# ---------------------------------------------------------------------------

async def handle_stripe_webhook(request: Request) -> JSONResponse:
    """
    POST /webhooks/stripe
    Handles Stripe subscription events with signature verification.
    """
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    stripe = get_stripe()
    if not stripe:
        return JSONResponse({"received": True})

    # Verify signature
    if STRIPE_WEBHOOK_SECRET and not STRIPE_WEBHOOK_SECRET.startswith("whsec_demo"):
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except Exception as exc:
            log.warning("Webhook signature invalid: %s", exc)
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        try:
            event = json.loads(payload)
        except Exception:
            return JSONResponse({"received": True})

    event_type = event.get("type", "") if isinstance(event, dict) else event.type
    log.info("Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        # Backup activation in case success URL wasn't reached
        session = event["data"]["object"] if isinstance(event, dict) else event.data.object
        session_id = session.get("id", "") if isinstance(session, dict) else session.id
        if session_id not in _pending_checkouts:
            log.info("Checkout %s already processed", session_id)

    elif event_type == "invoice.payment_failed":
        # Suspend key for this customer
        invoice     = event["data"]["object"] if isinstance(event, dict) else event.data.object
        customer_id = invoice.get("customer", "") if isinstance(invoice, dict) else invoice.customer
        _suspend_key_for_customer(customer_id)
        log.warning("Payment failed for customer %s — key suspended", customer_id)

    elif event_type == "invoice.paid":
        # Reactivate key if it was suspended
        invoice     = event["data"]["object"] if isinstance(event, dict) else event.data.object
        customer_id = invoice.get("customer", "") if isinstance(invoice, dict) else invoice.customer
        _reactivate_key_for_customer(customer_id)
        log.info("Payment succeeded for customer %s", customer_id)

    elif event_type == "customer.subscription.deleted":
        # Deactivate key permanently
        sub         = event["data"]["object"] if isinstance(event, dict) else event.data.object
        customer_id = sub.get("customer", "") if isinstance(sub, dict) else sub.customer
        _suspend_key_for_customer(customer_id)
        log.info("Subscription cancelled for customer %s", customer_id)

    return JSONResponse({"received": True})


def get_subscription_item_id(customer_id: str, tool_name: str) -> Optional[str]:
    """
    Get the Stripe subscription item ID for a specific tool and customer.
    Used by server.py to report metered usage to the correct subscription.
    """
    sub = _active_subscriptions.get(customer_id, {})
    items = sub.get("items", {})
    return items.get(tool_name)


# ---------------------------------------------------------------------------
# Key suspension helpers
# ---------------------------------------------------------------------------

def _suspend_key_for_customer(customer_id: str) -> None:
    from registration import _keys_issued
    for key, data in _keys_issued.items():
        if data.get("stripe_customer_id") == customer_id:
            data["suspended"] = True
            log.info("Key suspended for customer %s", customer_id)


def _reactivate_key_for_customer(customer_id: str) -> None:
    from registration import _keys_issued
    for key, data in _keys_issued.items():
        if data.get("stripe_customer_id") == customer_id:
            data.pop("suspended", None)
            log.info("Key reactivated for customer %s", customer_id)


# ---------------------------------------------------------------------------
# Success page
# ---------------------------------------------------------------------------

def _success_page(name: str, api_key: str, agreement_id: str, demo: bool = False) -> str:
    demo_notice = """<div style="background:#1a1a0a;border:1px solid #333;border-radius:8px;
        padding:.75rem 1rem;margin-bottom:1.2rem;font-size:.82rem;color:#888">
        ⚠ Demo mode — no payment required for first 100 calls.
        Add a payment method at <a href='/billing/checkout' style='color:#666'>/billing/checkout</a>
        before your free tier runs out.
    </div>""" if demo else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>API Key Ready — Scientific Tools MCP</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#0a0a0a;color:#e8e8e8;padding:2rem 1rem}}
    .wrap{{max-width:580px;margin:0 auto}}
    .icon{{font-size:2rem;margin-bottom:1rem}}
    h1{{font-size:1.4rem;font-weight:600;margin-bottom:.5rem;color:#fff}}
    p{{font-size:.9rem;color:#666;line-height:1.6;margin-bottom:.9rem}}
    .warn{{background:#1a1a0a;border:1px solid #333;border-radius:8px;
           padding:.75rem 1rem;font-size:.875rem;color:#888;margin:1.2rem 0}}
    .key-box{{background:#0f0f0f;border:1px solid #222;border-radius:8px;
              padding:1rem 1.2rem;margin:1.2rem 0}}
    .key-lbl{{font-size:.72rem;font-weight:500;color:#444;margin-bottom:.4rem;
              text-transform:uppercase;letter-spacing:.05em}}
    .key-val{{font-family:'Courier New',monospace;font-size:.88rem;
              font-weight:700;word-break:break-all;color:#fff}}
    .copy-btn{{margin-top:.6rem;padding:.4rem .9rem;background:#222;color:#fff;
               border:1px solid #333;border-radius:6px;font-size:.8rem;cursor:pointer}}
    .copy-btn:hover{{background:#333}}
    code{{background:#111;padding:.15rem .4rem;border-radius:4px;
          font-size:.82rem;color:#666}}
    .meta{{font-size:.72rem;color:#333;border-top:1px solid #111;
           padding-top:1rem;margin-top:1.5rem;line-height:1.6}}
    a{{color:#555}}
  </style>
</head>
<body>
<div class="wrap">
  <div class="icon">✓</div>
  <h1>You're in, {name.split()[0] if name != 'Anonymous' else 'there'}.</h1>
  <p>Your API key is ready. Add it to your agent configuration and start making calls.</p>

  {demo_notice}

  <div class="warn">
    ⚠ <strong>Save your API key now.</strong> It will not be shown again.
  </div>

  <div class="key-box">
    <div class="key-lbl">Your API Key</div>
    <div class="key-val" id="keyVal">{api_key}</div>
    <button class="copy-btn" onclick="copyKey()">Copy</button>
  </div>

  <p><strong style="color:#fff">MCP endpoint:</strong><br>
  <code>https://mcp-site.com/mcp</code></p>

  <p><strong style="color:#fff">Add to your agent config:</strong><br>
  <code>{{"Authorization": "Bearer {api_key}"}}</code></p>

  <p><strong style="color:#fff">Discover tools:</strong><br>
  <code>POST /mcp → {{"method": "tools/list"}}</code></p>

  <p>Questions? <a href="mailto:shomechakraborty@gmail.com">shomechakraborty@gmail.com</a></p>

  <div class="meta">
    Agreement ID: {agreement_id}<br>
    By using this key you agree to the
    <a href="/terms">Terms of Service</a> and
    <a href="/privacy">Privacy Policy</a>.
  </div>
</div>
<script>
function copyKey() {{
  navigator.clipboard.writeText('{api_key}').then(() => {{
    const btn = document.querySelector('.copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 2000);
  }});
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Rate limiting for /keys/request (prevent spam)
# ---------------------------------------------------------------------------

_key_request_ips: dict[str, list] = {}


def check_key_request_rate_limit(ip: str) -> bool:
    """Allow max 5 key requests per IP per hour."""
    import time
    now = time.time()
    window = _key_request_ips.get(ip, [])
    window = [t for t in window if now - t < 3600]
    if len(window) >= 5:
        return False
    window.append(now)
    _key_request_ips[ip] = window
    return True


# ---------------------------------------------------------------------------
# Mount routes
# ---------------------------------------------------------------------------

def mount_billing_routes(app) -> None:
    app.get("/")(handle_landing)
    app.post("/billing/checkout")(handle_checkout_post)
    app.get("/billing/success")(handle_billing_success)
    app.get("/billing/cancel")(handle_billing_cancel)
    log.info("Billing routes mounted: /, /billing/checkout, /billing/success, /billing/cancel")
