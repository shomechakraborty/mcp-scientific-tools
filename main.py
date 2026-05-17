#!/usr/bin/env python3
"""
MCP Server — Full System Entry Point
======================================
Registers all tools, boots the server, and runs a live demo.

Production deployment:
  1. Set env vars (see .env.example below)
  2. python main.py --serve          # starts uvicorn on port 8000
  3. Add SSL via nginx reverse proxy
  4. Submit to mcp.so, Glama.ai, Anthropic MCP directory

.env.example:
  STRIPE_SECRET_KEY=sk_live_...
  STRIPE_WEBHOOK_SECRET=whsec_...
  NOAA_API_TOKEN=your_noaa_token
  NASA_API_KEY=your_nasa_key
  STRIPE_PRICE_LITERATURE=price_...
  STRIPE_PRICE_COMPOUND=price_...
  STRIPE_PRICE_GPU=price_...
  STRIPE_PRICE_PATENT=price_...
  STRIPE_PRICE_SCIDATA=price_...
  STRIPE_PRICE_ANALYTICS=price_...
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from server import registry, app
from registration import mount_registration_routes, get_issued_keys
from billing import mount_billing_routes
from tools.literature_search import register as reg_literature
from tools.compound_lookup    import register as reg_compound
from tools.gpu_spot_prices    import register as reg_gpu
from tools.patent_search      import register as reg_patent
from tools.scientific_data    import register as reg_scidata
from tools.analytics          import register as reg_analytics

# Mount registration routes (self-serve key issuance)
mount_registration_routes(app)

# Mount billing routes (landing page, Stripe checkout)
mount_billing_routes(app)

# Load persisted keys from database into memory on startup
from registration import _load_keys_from_db
_load_keys_from_db()

# Register all tools
reg_literature(registry)
reg_compound(registry)
reg_gpu(registry)
reg_patent(registry)
reg_scidata(registry)
reg_analytics(registry)

if __name__ == "__main__":
    if "--serve" in sys.argv:
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
    else:
        from server import _demo
        _demo()
