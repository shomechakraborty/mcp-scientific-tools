"""
Tool Response Validator
========================
Validates tool outputs before they are returned to agents.
Catches cases where external APIs return empty, malformed,
or clearly wrong data — preventing bad data from reaching agents.

Each validator returns (is_valid, warning_message).
Warnings are logged but don't block the response — the agent
still gets the data, but the issue is recorded for monitoring.
"""

import logging

log = logging.getLogger("validator")


def validate_literature_search(result: dict) -> tuple[bool, str]:
    if "error" in result:
        return False, f"Tool returned error: {result['error']}"
    if result.get("total_results", 0) == 0:
        return True, "No results found — may be valid for obscure queries"
    results = result.get("results", [])
    if not results:
        return False, "total_results > 0 but results list is empty"
    first = results[0]
    if not first.get("title"):
        return False, "First result has no title"
    return True, ""


def validate_compound_lookup(result: dict) -> tuple[bool, str]:
    pubchem = result.get("pubchem", {})
    if "error" in pubchem:
        return False, f"PubChem error: {pubchem['error']}"
    if not pubchem.get("molecular_formula"):
        return False, "No molecular formula returned"
    return True, ""


def validate_gpu_spot_prices(result: dict) -> tuple[bool, str]:
    if result.get("total_slots", 0) == 0:
        return False, "No GPU slots returned"
    if not result.get("best_by_gpu_type"):
        return False, "No best prices by GPU type"
    return True, ""


def validate_patent_search(result: dict) -> tuple[bool, str]:
    if "error" in result:
        return False, f"Tool returned error: {result['error']}"
    # Zero results is valid for niche queries
    return True, ""


def validate_scientific_data(result: dict) -> tuple[bool, str]:
    if "error" in result:
        return False, f"Tool returned error: {result['error']}"
    dataset = result.get("dataset", "")
    if dataset == "earthquakes":
        if "events" not in result:
            return False, "No events field in earthquake response"
    return True, ""


def validate_analytics(result: dict) -> tuple[bool, str]:
    if "error" in result:
        return False, f"Analytics error: {result['error']}"
    return True, ""


VALIDATORS = {
    "literature_search":       validate_literature_search,
    "compound_lookup":         validate_compound_lookup,
    "gpu_spot_prices":         validate_gpu_spot_prices,
    "patent_prior_art_search": validate_patent_search,
    "scientific_data":         validate_scientific_data,
    "analytics":               validate_analytics,
}


def validate(tool_name: str, result: dict) -> tuple[bool, str]:
    """
    Validate a tool result. Returns (is_valid, warning).
    Logs warnings but never blocks response delivery.
    """
    validator = VALIDATORS.get(tool_name)
    if not validator:
        return True, ""

    try:
        is_valid, warning = validator(result)
        if not is_valid:
            log.warning("Tool %s validation failed: %s", tool_name, warning)
        return is_valid, warning
    except Exception as exc:
        log.error("Validator crashed for %s: %s", tool_name, exc)
        return True, ""  # Don't block on validator errors
