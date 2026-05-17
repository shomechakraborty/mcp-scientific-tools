# Scientific Tools MCP Server

An MCP-compatible server providing high-value scientific tools for AI agents.
Earn per tool call. Zero upfront capital. Fully automated.

## Tools

| Tool | Price/call | Description |
|---|---|---|
| `literature_search` | $0.020 | PubMed + arXiv + Semantic Scholar |
| `compound_lookup` | $0.010 | PubChem + ChEMBL molecular properties |
| `gpu_spot_prices` | $0.005 | Live GPU spot prices across 4 providers |
| `patent_prior_art_search` | $0.050 | USPTO + EPO patent databases |
| `scientific_data` | $0.003 | USGS earthquakes, NASA, OpenAQ air quality |
| `analytics` | $0.001 | Usage stats and revenue reporting |

## Quick start

```bash
# 1. Install dependencies
pip install fastapi uvicorn stripe pydantic aiohttp

# 2. Set environment variables
cp .env.example .env
# Edit .env with your keys

# 3. Run demo (no keys needed)
python main.py

# 4. Start production server
python main.py --serve
```

## Environment variables

```bash
# Required for billing
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Stripe metered price IDs (create in Stripe dashboard)
STRIPE_PRICE_LITERATURE=price_...
STRIPE_PRICE_COMPOUND=price_...
STRIPE_PRICE_GPU=price_...
STRIPE_PRICE_PATENT=price_...
STRIPE_PRICE_SCIDATA=price_...
STRIPE_PRICE_ANALYTICS=price_...

# Optional — improves data access limits
NOAA_API_TOKEN=...        # https://www.ncdc.noaa.gov/cdo-web/token
NASA_API_KEY=...          # https://api.nasa.gov/
```

## Deployment (VPS)

```bash
# On a fresh Ubuntu 22.04 VPS ($6/mo Hetzner)

# Install Python
sudo apt update && sudo apt install python3-pip python3-venv nginx certbot -y

# Clone and install
git clone https://github.com/yourname/mcp-scientific-tools
cd mcp-scientific-tools
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run as service
sudo nano /etc/systemd/system/mcp-server.service
# [Unit]
# Description=MCP Scientific Tools Server
# [Service]
# WorkingDirectory=/home/ubuntu/mcp-scientific-tools
# ExecStart=/home/ubuntu/mcp-scientific-tools/venv/bin/python main.py --serve
# Restart=always
# [Install]
# WantedBy=multi-user.target

sudo systemctl enable mcp-server && sudo systemctl start mcp-server

# SSL via nginx + certbot
sudo certbot --nginx -d your-domain.com
```

## Directory submissions (one-time, ~30 minutes)

1. **mcp.so** — https://mcp.so/submit
   Submit: server name, endpoint URL, tool descriptions

2. **Glama.ai** — https://glama.ai/mcp/servers/submit
   Submit: GitHub repo URL

3. **Anthropic MCP directory** — https://github.com/modelcontextprotocol/servers
   Open a PR adding your server to the README

4. **GitHub topic** — Add `mcp-server` tag to your repo
   Automatically discoverable by agents scanning GitHub

## Stripe setup

1. Create a Stripe account at stripe.com
2. Create a product: "Scientific Tools MCP"
3. For each tool, create a metered price:
   - Billing: recurring, monthly
   - Metered usage: sum of usage during period
   - Price per unit: tool's per-call rate
4. Copy each price ID (price_...) to your .env

## Agent integration example

```python
import anthropic

client = anthropic.Anthropic()

# Add your MCP server
response = client.beta.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    tools=[{
        "type": "custom",
        "name": "scientific_tools",
        "description": "Scientific research tools",
        "mcp_server": {
            "url": "https://your-domain.com/mcp",
            "auth": {"type": "bearer", "token": "mcp-key-..."}
        }
    }],
    messages=[{
        "role": "user",
        "content": "Search for recent papers on CRISPR cancer therapy"
    }]
)
```

## Legal disclaimer and terms of service

**BY USING THIS SERVICE OR ANY API KEY ISSUED BY THIS SERVICE, YOU AGREE TO
THESE TERMS, INCLUDING THE DISCLAIMER THAT THE SERVICE IS PROVIDED AS IS
WITHOUT WARRANTY, DATA IS SOURCED FROM THIRD-PARTY APIS AND MAY BE INACCURATE,
AND OPERATOR LIABILITY IS LIMITED TO FEES PAID IN THE PRECEDING 30 DAYS.
IF YOU DO NOT AGREE, DO NOT USE THIS SERVICE OR ITS API KEYS.**

---

### 1. No warranties

This service is provided **"as is" and "as available" without warranty of
any kind**, express or implied, including but not limited to warranties of
merchantability, fitness for a particular purpose, or accuracy. The service
retrieves data from third-party public APIs (PubMed, PubChem, USPTO, USGS,
NASA, OpenAQ, and others) over which the operator has no control. That data
may be incomplete, inaccurate, outdated, or unavailable at any time without
notice.

### 2. Not professional advice

Data and outputs provided by this service **do not constitute and must not
be relied upon as** medical, clinical, legal, patent, financial, pharmaceutical,
toxicological, or safety advice. Users requiring professional advice must
consult qualified licensed professionals. The operator expressly disclaims
responsibility for any decisions made based on outputs from this service.

Specifically:
- Literature search results are not a substitute for systematic review by qualified researchers
- Compound property data is not a substitute for laboratory analysis by qualified chemists
- Patent search results are not a substitute for freedom-to-operate analysis by a licensed patent attorney
- Earthquake and environmental data are not a substitute for official emergency management guidance

### 3. Limitation of liability

To the maximum extent permitted by applicable law, the operator's aggregate
liability for any claims arising from or related to this service **shall not
exceed the total fees paid by the claimant in the 30 days preceding the claim**.
The operator shall not be liable for any indirect, incidental, consequential,
or punitive damages of any kind.

### 4. Data sources

This service retrieves data from: PubMed/NCBI, arXiv, Semantic Scholar,
PubChem, ChEMBL, USPTO, EPO/Espacenet, USGS, NASA, and OpenAQ. Each source
is subject to its own terms and accuracy limitations. The operator makes no
representation regarding the accuracy or completeness of data from any of
these sources.

### 5. Acceptable use

You agree not to use this service to make clinical, medical, or safety-critical
decisions without independent professional verification, to circumvent rate
limits or billing mechanisms, or to engage in any activity that violates
applicable laws or regulations.

### 6. Service availability

The operator does not guarantee any specific level of uptime, availability,
or response time. The service may be interrupted, modified, suspended, or
discontinued at any time with or without notice.

### 7. Privacy

Query parameters are processed in memory solely to fulfil each request and
are not stored beyond the duration of each individual request. Usage metadata
(tool name, timestamp, call volume) is retained for billing and analytics.
No personally identifiable information is knowingly collected or transmitted
to third parties beyond what is required for payment processing (Stripe).

### 8. Governing law

These terms are governed by the laws of the United States and the state in
which the operator is domiciled, without regard to conflict of law provisions.

---

Full terms of service: `https://yourdomain.com/terms`

Complete legal text: see `DISCLAIMER.py` in this repository

## Revenue projection

At 5 tools × 1,000 calls/day × $0.01 avg price = $50/day = $1,500/month

Scale levers:
- More tools → more call volume
- Better tools → higher per-call price
- More agent integrations → more calls automatically
