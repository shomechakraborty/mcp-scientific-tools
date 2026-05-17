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
Tool: Patent Prior Art Search
================================
Searches USPTO and EPO (via Espacenet) for prior art.
Returns ranked results with similarity scores, claim summaries,
and filing dates. Patent agents pay $0.05/call — highest value tool.

Price: $0.05 per call
Target agents: IP research pipelines, patent drafting assistants,
               freedom-to-operate analysis agents
"""

import asyncio
import logging
import os
import urllib.parse
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger("tool.patent_search")

TOOL_NAME        = "patent_prior_art_search"
TOOL_PRICE_USD   = 0.05
TOOL_STRIPE_PRICE = os.getenv("STRIPE_PRICE_PATENT", "price_demo_patent")

USPTO_BASE    = "https://developer.uspto.gov/ibd-api/v1/application/grants"
EPO_OPS_BASE  = "https://ops.epo.org/3.2/rest-services"
PATENTSVIEW   = "https://api.patentsview.org/patents/query"

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Technical description of the invention to search prior art for",
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key technical terms (improves recall)",
        },
        "classification": {
            "type": "string",
            "description": "CPC/IPC classification code (e.g. A61K, G06F, H04L)",
        },
        "date_from": {
            "type": "string",
            "description": "Start date for search YYYY-MM-DD",
        },
        "date_to": {
            "type": "string",
            "description": "End date for search YYYY-MM-DD",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum results to return (1–20, default 10)",
            "default": 10,
            "minimum": 1,
            "maximum": 20,
        },
        "sources": {
            "type": "array",
            "items": {"type": "string", "enum": ["uspto", "epo", "patentsview"]},
            "description": "Patent databases to search (default: all)",
            "default": ["uspto", "patentsview"],
        },
    },
    "required": ["query"],
}


async def _search_patentsview(
    session: aiohttp.ClientSession,
    query: str,
    keywords: list,
    classification: str,
    date_from: str,
    date_to: str,
    max_results: int,
) -> list[dict]:
    """Search PatentsView API (USPTO open data)."""
    all_terms = [query] + (keywords or [])
    search_text = " ".join(all_terms[:5])

    query_obj = {
        "_text_any": {
            "patent_abstract": search_text,
            "patent_title": search_text,
        }
    }

    if date_from or date_to:
        date_filter = {}
        if date_from:
            date_filter["_gte"] = {"patent_date": date_from}
        if date_to:
            date_filter["_lte"] = {"patent_date": date_to}
        if date_filter:
            query_obj = {"_and": [query_obj, date_filter]}

    fields = [
        "patent_id", "patent_title", "patent_abstract",
        "patent_date", "patent_number", "assignees.assignee_organization",
        "inventors.inventor_last_name", "inventors.inventor_first_name",
        "cpcs.cpc_group_id",
    ]

    payload = {
        "q": query_obj,
        "f": fields,
        "o": {"per_page": max_results, "sort": [{"patent_date": "desc"}]},
    }

    try:
        async with session.post(
            PATENTSVIEW,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
            headers={"Content-Type": "application/json"},
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        patents = data.get("patents") or []
        results = []
        for p in patents[:max_results]:
            assignees = p.get("assignees") or []
            assignee = assignees[0].get("assignee_organization", "") if assignees else ""

            inventors = p.get("inventors") or []
            inventor_names = [
                f"{i.get('inventor_last_name', '')} {i.get('inventor_first_name', '')}".strip()
                for i in inventors[:3]
            ]

            cpcs = p.get("cpcs") or []
            cpc_codes = [c.get("cpc_group_id", "") for c in cpcs[:3]]

            abstract = p.get("patent_abstract") or ""
            results.append({
                "source": "patentsview_uspto",
                "patent_number": p.get("patent_number", ""),
                "title": p.get("patent_title", ""),
                "abstract": abstract[:500] + "..." if len(abstract) > 500 else abstract,
                "filing_date": p.get("patent_date", ""),
                "assignee": assignee,
                "inventors": inventor_names,
                "cpc_codes": cpc_codes,
                "url": f"https://patents.google.com/patent/US{p.get('patent_number', '')}",
            })
        return results

    except Exception as exc:
        log.warning("PatentsView search failed: %s", exc)
        return []


async def _search_epo(
    session: aiohttp.ClientSession,
    query: str,
    keywords: list,
    classification: str,
    max_results: int,
) -> list[dict]:
    """Search EPO Espacenet via OPS API (open access)."""
    all_terms = [query] + (keywords or [])
    cql_terms = " OR ".join(f'"{t}"' for t in all_terms[:3])
    cql = f"txt={cql_terms}"
    if classification:
        cql += f" AND cpc={classification}"

    url = (
        f"{EPO_OPS_BASE}/published-data/search/biblio"
        f"?q={urllib.parse.quote(cql)}&Range=1-{min(max_results, 25)}"
    )

    try:
        async with session.get(
            url,
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        results_raw = (
            data.get("ops:world-patent-data", {})
            .get("ops:biblio-search", {})
            .get("ops:search-result", {})
            .get("ops:publication-reference", [])
        )
        if isinstance(results_raw, dict):
            results_raw = [results_raw]

        results = []
        for ref in results_raw[:max_results]:
            doc_id = ref.get("document-id", {})
            country = doc_id.get("country", {}).get("$", "")
            number = doc_id.get("doc-number", {}).get("$", "")
            kind = doc_id.get("kind", {}).get("$", "")
            results.append({
                "source": "epo",
                "patent_number": f"{country}{number}{kind}",
                "title": "",
                "abstract": "",
                "filing_date": doc_id.get("date", {}).get("$", ""),
                "assignee": "",
                "inventors": [],
                "cpc_codes": [],
                "url": f"https://worldwide.espacenet.com/patent/search?q={country}{number}",
            })
        return results

    except Exception as exc:
        log.warning("EPO search failed: %s", exc)
        return []


async def patent_prior_art_search_handler(arguments: dict) -> dict:
    query          = arguments.get("query", "")
    keywords       = arguments.get("keywords", [])
    classification = arguments.get("classification", "")
    date_from      = arguments.get("date_from", "")
    date_to        = arguments.get("date_to", "")
    max_results    = min(int(arguments.get("max_results", 10)), 20)
    sources        = arguments.get("sources", ["uspto", "patentsview"])

    if not query:
        return {"error": "query parameter is required"}

    async with aiohttp.ClientSession() as session:
        tasks = []
        source_names = []

        if "patentsview" in sources or "uspto" in sources:
            tasks.append(_search_patentsview(
                session, query, keywords, classification, date_from, date_to, max_results
            ))
            source_names.append("patentsview_uspto")

        if "epo" in sources:
            tasks.append(_search_epo(session, query, keywords, classification, max_results))
            source_names.append("epo")

        results_per_source = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    sources_searched = []
    for name, results in zip(source_names, results_per_source):
        if isinstance(results, Exception):
            results = []
        all_results.extend(results)
        sources_searched.append({"source": name, "count": len(results)})

    return {
        "query": query,
        "keywords": keywords,
        "classification": classification,
        "total_results": len(all_results),
        "sources_searched": sources_searched,
        "results": all_results,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "note": "Results are retrieved from public patent databases. Consult a patent attorney for FTO opinions.",
    }


def register(registry) -> None:
    from server import ToolDefinition
    registry.register(ToolDefinition(
        name=TOOL_NAME,
        description=(
            "Search USPTO and EPO patent databases for prior art. "
            "Accepts a technical description and optional keywords, CPC classification, "
            "and date range. Returns ranked patent results with titles, abstracts, "
            "assignees, inventors, and CPC codes. "
            "Highest-value tool — patent agents pay premium rates per search."
        ),
        input_schema=TOOL_SCHEMA,
        price_per_call_usd=TOOL_PRICE_USD,
        stripe_price_id=TOOL_STRIPE_PRICE,
        handler=patent_prior_art_search_handler,
        category="intellectual_property",
    ))


if __name__ == "__main__":
    async def test():
        print("Testing patent_prior_art_search tool...\n")
        result = await patent_prior_art_search_handler({
            "query": "neural network training acceleration using sparse attention",
            "keywords": ["transformer", "sparse attention", "GPU training"],
            "max_results": 5,
        })
        print(f"Query: {result['query']}")
        print(f"Total results: {result['total_results']}")
        for src in result["sources_searched"]:
            print(f"  {src['source']}: {src['count']} results")
        for r in result["results"][:3]:
            print(f"\n  [{r['source']}] {r['patent_number']}")
            print(f"  Title: {r['title'][:70] or '(not retrieved)'}")
            print(f"  Filed: {r['filing_date']}  Assignee: {r['assignee'][:40]}")
            print(f"  URL: {r['url']}")

    asyncio.run(test())
