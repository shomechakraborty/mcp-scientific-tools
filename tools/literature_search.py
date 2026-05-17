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
Tool: Scientific Literature Search
====================================
Searches PubMed, arXiv, and Semantic Scholar simultaneously.
Returns structured results with abstracts, citations, and relevance scores.

Price: $0.02 per call
Target agents: research automation, drug discovery, systematic review pipelines

APIs used (all free, no key required for basic access):
  - PubMed E-utilities (NCBI) — biomedical literature
  - arXiv API — preprints across sciences
  - Semantic Scholar API — cross-domain, citation graph
"""

import asyncio
import json
import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

import aiohttp

log = logging.getLogger("tool.literature_search")

TOOL_NAME        = "literature_search"
TOOL_PRICE_USD   = 0.02
TOOL_STRIPE_PRICE = os.getenv("STRIPE_PRICE_LITERATURE", "price_demo_literature")

NCBI_BASE        = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ARXIV_BASE       = "https://export.arxiv.org/api/query"
S2_BASE          = "https://api.semanticscholar.org/graph/v1"

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Search query — natural language or Boolean operators supported"
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum results per source (1–20, default 5)",
            "default": 5,
            "minimum": 1,
            "maximum": 20,
        },
        "sources": {
            "type": "array",
            "items": {"type": "string", "enum": ["pubmed", "arxiv", "semantic_scholar"]},
            "description": "Sources to search (default: all three)",
            "default": ["pubmed", "arxiv", "semantic_scholar"],
        },
        "year_from": {
            "type": "integer",
            "description": "Filter results from this year onwards",
        },
        "year_to": {
            "type": "integer",
            "description": "Filter results up to this year",
        },
        "fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: filter by research field (e.g. ['biology', 'chemistry'])",
        },
    },
    "required": ["query"],
}


# ---------------------------------------------------------------------------
# PubMed search
# ---------------------------------------------------------------------------

async def _search_pubmed(
    session: aiohttp.ClientSession,
    query: str,
    max_results: int,
    year_from: Optional[int],
    year_to: Optional[int],
) -> list[dict]:
    """Search PubMed E-utilities for biomedical literature."""
    date_filter = ""
    if year_from or year_to:
        y_from = year_from or 1900
        y_to   = year_to   or datetime.now().year
        date_filter = f"&mindate={y_from}/01/01&maxdate={y_to}/12/31&datetype=pdat"

    # Step 1: esearch to get PMIDs
    search_url = (
        f"{NCBI_BASE}/esearch.fcgi"
        f"?db=pubmed&term={urllib.parse.quote(query)}"
        f"&retmax={max_results}&sort=relevance&retmode=json{date_filter}"
    )

    try:
        async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
            if not pmids:
                return []

        # Step 2: efetch to get abstracts
        fetch_url = (
            f"{NCBI_BASE}/efetch.fcgi"
            f"?db=pubmed&id={','.join(pmids)}&retmode=json&rettype=abstract"
        )
        async with session.get(fetch_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            raw = await resp.text()

        # PubMed efetch JSON can be inconsistent — parse defensively
        try:
            fetch_data = json.loads(raw)
            articles = fetch_data.get("PubmedArticleSet", {})
            if isinstance(articles, dict):
                articles = articles.get("PubmedArticle", [])
            if not isinstance(articles, list):
                articles = [articles]
        except Exception:
            articles = []

        results = []
        for article in articles[:max_results]:
            try:
                medline = article.get("MedlineCitation", {})
                article_info = medline.get("Article", {})
                title = article_info.get("ArticleTitle", "")
                if isinstance(title, dict):
                    title = title.get("#text", "")

                abstract_data = article_info.get("Abstract", {})
                abstract_text = abstract_data.get("AbstractText", "")
                if isinstance(abstract_text, list):
                    abstract_text = " ".join(
                        t.get("#text", t) if isinstance(t, dict) else t
                        for t in abstract_text
                    )
                elif isinstance(abstract_text, dict):
                    abstract_text = abstract_text.get("#text", "")

                journal_info = article_info.get("Journal", {})
                journal = journal_info.get("Title", "")
                pub_date = journal_info.get("JournalIssue", {}).get("PubDate", {})
                year = pub_date.get("Year", "")

                pmid = medline.get("PMID", {})
                if isinstance(pmid, dict):
                    pmid = pmid.get("#text", "")

                authors_list = article_info.get("AuthorList", {})
                if isinstance(authors_list, dict):
                    authors_list = authors_list.get("Author", [])
                if not isinstance(authors_list, list):
                    authors_list = [authors_list]

                authors = []
                for a in authors_list[:3]:
                    if isinstance(a, dict):
                        last = a.get("LastName", "")
                        first = a.get("ForeName", "")
                        if last:
                            authors.append(f"{last} {first}".strip())

                results.append({
                    "source": "pubmed",
                    "id": f"pmid:{pmid}",
                    "title": str(title),
                    "abstract": str(abstract_text)[:500] + "..." if len(str(abstract_text)) > 500 else str(abstract_text),
                    "authors": authors,
                    "journal": journal,
                    "year": str(year),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "citation_count": None,
                })
            except Exception as e:
                log.debug("PubMed parse error: %s", e)
                continue

        return results

    except Exception as exc:
        log.warning("PubMed search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# arXiv search
# ---------------------------------------------------------------------------

async def _search_arxiv(
    session: aiohttp.ClientSession,
    query: str,
    max_results: int,
    year_from: Optional[int],
    year_to: Optional[int],
) -> list[dict]:
    """Search arXiv preprints."""
    import xml.etree.ElementTree as ET

    params = {
        "search_query": f"all:{query}",
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_BASE}?{urllib.parse.urlencode(params)}"

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(text)
        entries = root.findall("atom:entry", ns)

        results = []
        for entry in entries[:max_results]:
            try:
                arxiv_id_raw = entry.find("atom:id", ns)
                arxiv_id = arxiv_id_raw.text.split("/abs/")[-1] if arxiv_id_raw is not None else ""

                title_el = entry.find("atom:title", ns)
                title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""

                summary_el = entry.find("atom:summary", ns)
                summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None else ""

                published_el = entry.find("atom:published", ns)
                published = published_el.text[:4] if published_el is not None else ""

                if year_from and published and int(published) < year_from:
                    continue
                if year_to and published and int(published) > year_to:
                    continue

                authors = [
                    a.find("atom:name", ns).text
                    for a in entry.findall("atom:author", ns)[:3]
                    if a.find("atom:name", ns) is not None
                ]

                results.append({
                    "source": "arxiv",
                    "id": f"arxiv:{arxiv_id}",
                    "title": title,
                    "abstract": summary[:500] + "..." if len(summary) > 500 else summary,
                    "authors": authors,
                    "journal": "arXiv preprint",
                    "year": published,
                    "url": f"https://arxiv.org/abs/{arxiv_id}",
                    "citation_count": None,
                })
            except Exception as e:
                log.debug("arXiv parse error: %s", e)
                continue

        return results

    except Exception as exc:
        log.warning("arXiv search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Semantic Scholar search
# ---------------------------------------------------------------------------

async def _search_semantic_scholar(
    session: aiohttp.ClientSession,
    query: str,
    max_results: int,
    year_from: Optional[int],
    year_to: Optional[int],
) -> list[dict]:
    """Search Semantic Scholar for cross-domain papers with citation counts."""
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,authors,year,citationCount,externalIds,venue",
    }
    if year_from:
        params["year"] = f"{year_from}-"
    if year_to and year_from:
        params["year"] = f"{year_from}-{year_to}"

    url = f"{S2_BASE}/paper/search?{urllib.parse.urlencode(params)}"

    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"User-Agent": "MCP-Scientific-Tools/1.0"},
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()

        papers = data.get("data", [])
        results = []

        for paper in papers[:max_results]:
            try:
                external_ids = paper.get("externalIds", {})
                paper_id = (
                    external_ids.get("DOI")
                    or external_ids.get("ArXiv")
                    or paper.get("paperId", "")
                )

                authors = [
                    a.get("name", "")
                    for a in paper.get("authors", [])[:3]
                ]

                abstract = paper.get("abstract") or ""

                results.append({
                    "source": "semantic_scholar",
                    "id": f"s2:{paper.get('paperId', '')}",
                    "title": paper.get("title", ""),
                    "abstract": abstract[:500] + "..." if len(abstract) > 500 else abstract,
                    "authors": authors,
                    "journal": paper.get("venue", ""),
                    "year": str(paper.get("year", "")),
                    "url": f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}",
                    "citation_count": paper.get("citationCount"),
                })
            except Exception as e:
                log.debug("S2 parse error: %s", e)
                continue

        return results

    except Exception as exc:
        log.warning("Semantic Scholar search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

async def literature_search_handler(arguments: dict) -> dict:
    """Main handler — called by MCP server on each tool invocation."""
    query       = arguments.get("query", "")
    max_results = min(int(arguments.get("max_results", 5)), 20)
    sources     = arguments.get("sources", ["pubmed", "arxiv", "semantic_scholar"])
    year_from   = arguments.get("year_from")
    year_to     = arguments.get("year_to")

    if not query:
        return {"error": "query parameter is required"}

    async with aiohttp.ClientSession() as session:
        tasks = []
        if "pubmed" in sources:
            tasks.append(_search_pubmed(session, query, max_results, year_from, year_to))
        if "arxiv" in sources:
            tasks.append(_search_arxiv(session, query, max_results, year_from, year_to))
        if "semantic_scholar" in sources:
            tasks.append(_search_semantic_scholar(session, query, max_results, year_from, year_to))

        results_per_source = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    sources_searched = []
    for i, (source, results) in enumerate(zip(
        [s for s in ["pubmed", "arxiv", "semantic_scholar"] if s in sources],
        results_per_source,
    )):
        if isinstance(results, Exception):
            log.warning("Source %s failed: %s", source, results)
            results = []
        all_results.extend(results)
        sources_searched.append({"source": source, "results_count": len(results)})

    # Sort by citation count where available, then by year
    all_results.sort(
        key=lambda r: (r.get("citation_count") or -1, r.get("year") or ""),
        reverse=True,
    )

    return {
        "query": query,
        "total_results": len(all_results),
        "sources_searched": sources_searched,
        "results": all_results,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(registry) -> None:
    from server import ToolDefinition
    registry.register(ToolDefinition(
        name=TOOL_NAME,
        description=(
            "Search scientific literature across PubMed, arXiv, and Semantic Scholar. "
            "Returns structured results with titles, abstracts, authors, publication years, "
            "and citation counts. Supports date range filtering and field-specific queries."
        ),
        input_schema=TOOL_SCHEMA,
        price_per_call_usd=TOOL_PRICE_USD,
        stripe_price_id=TOOL_STRIPE_PRICE,
        handler=literature_search_handler,
        category="research",
    ))


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    async def test():
        print("Testing literature_search tool...\n")
        result = await literature_search_handler({
            "query": "CRISPR Cas9 cancer immunotherapy",
            "max_results": 3,
            "sources": ["pubmed", "arxiv", "semantic_scholar"],
        })
        print(f"Query: {result['query']}")
        print(f"Total results: {result['total_results']}")
        for src in result['sources_searched']:
            print(f"  {src['source']}: {src['results_count']} results")
        print()
        for r in result['results'][:5]:
            print(f"  [{r['source']}] {r['title'][:70]}")
            print(f"    Year: {r.get('year')}  Citations: {r.get('citation_count')}  Authors: {', '.join(r['authors'][:2])}")
            print(f"    URL: {r['url']}")
            print()

    asyncio.run(test())
