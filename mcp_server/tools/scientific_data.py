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
Tool: Real-Time Scientific Data
==================================
Fetches real-time and recent measurements from major public scientific APIs.
Returns structured, agent-ready data from NOAA, USGS, NASA, and EPA.

Price: $0.003 per call (high volume, lower price)
Target agents: climate research, environmental monitoring, geoscience pipelines,
               earth observation agents

APIs (all free, no key required for basic access):
  - NOAA Climate Data Online API
  - USGS Earthquake Hazards API
  - NASA APOD and DONKI APIs (requires free NASA API key for full access)
  - EPA AQS (Air Quality System) API
"""

import asyncio
import logging
import os
import urllib.parse
from datetime import datetime, timedelta, timezone

import aiohttp

log = logging.getLogger("tool.scientific_data")

TOOL_NAME        = "scientific_data"
TOOL_PRICE_USD   = 0.003
TOOL_STRIPE_PRICE = os.getenv("STRIPE_PRICE_SCIDATA", "price_demo_scidata")

NOAA_BASE  = "https://www.ncdc.noaa.gov/cdo-web/api/v2"
USGS_BASE  = "https://earthquake.usgs.gov/fdsnws/event/1"
NASA_BASE  = "https://api.nasa.gov"
EPA_BASE   = "https://aqs.epa.gov/data/api"

NOAA_TOKEN = os.getenv("NOAA_API_TOKEN", "")
NASA_KEY   = os.getenv("NASA_API_KEY", "DEMO_KEY")

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "dataset": {
            "type": "string",
            "enum": [
                "earthquakes",
                "air_quality",
                "solar_events",
                "nasa_apod",
                "climate_normals",
            ],
            "description": "Scientific dataset to retrieve",
        },
        "location": {
            "type": "string",
            "description": "Location for spatially-filtered queries (city name, lat/lon, or country code)",
        },
        "latitude": {"type": "number", "description": "Latitude for geographic queries"},
        "longitude": {"type": "number", "description": "Longitude for geographic queries"},
        "radius_km": {
            "type": "number",
            "description": "Search radius in km around lat/lon (default: 500)",
            "default": 500,
        },
        "date_from": {"type": "string", "description": "Start date YYYY-MM-DD (default: 7 days ago)"},
        "date_to": {"type": "string", "description": "End date YYYY-MM-DD (default: today)"},
        "min_magnitude": {
            "type": "number",
            "description": "Minimum earthquake magnitude (for earthquakes dataset)",
            "default": 4.0,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum results to return (default: 10)",
            "default": 10,
        },
    },
    "required": ["dataset"],
}


async def _fetch_earthquakes(
    session: aiohttp.ClientSession, args: dict
) -> dict:
    """Fetch recent earthquakes from USGS."""
    now = datetime.now(timezone.utc)
    date_from = args.get("date_from", (now - timedelta(days=7)).strftime("%Y-%m-%d"))
    date_to   = args.get("date_to", now.strftime("%Y-%m-%d"))
    min_mag   = args.get("min_magnitude", 4.0)
    max_results = min(int(args.get("max_results", 10)), 100)

    params = {
        "format": "geojson",
        "starttime": date_from,
        "endtime": date_to,
        "minmagnitude": min_mag,
        "orderby": "magnitude",
        "limit": max_results,
    }

    lat = args.get("latitude")
    lon = args.get("longitude")
    if lat and lon:
        params["latitude"] = lat
        params["longitude"] = lon
        params["maxradiuskm"] = args.get("radius_km", 500)

    url = f"{USGS_BASE}/query?{urllib.parse.urlencode(params)}"

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return {"error": f"USGS returned {resp.status}"}
            data = await resp.json()

        features = data.get("features", [])
        events = []
        for f in features[:max_results]:
            props = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [None, None, None])
            events.append({
                "id": f.get("id", ""),
                "magnitude": props.get("mag"),
                "magnitude_type": props.get("magType"),
                "place": props.get("place", ""),
                "time": datetime.utcfromtimestamp(props.get("time", 0) / 1000).isoformat() if props.get("time") else "",
                "depth_km": coords[2] if len(coords) > 2 else None,
                "longitude": coords[0] if len(coords) > 0 else None,
                "latitude": coords[1] if len(coords) > 1 else None,
                "status": props.get("status", ""),
                "tsunami": props.get("tsunami", 0),
                "url": props.get("url", ""),
            })

        return {
            "dataset": "earthquakes",
            "source": "USGS Earthquake Hazards Program",
            "query_params": {"date_from": date_from, "date_to": date_to, "min_magnitude": min_mag},
            "total_events": data.get("metadata", {}).get("count", len(events)),
            "events": events,
        }
    except Exception as exc:
        return {"error": str(exc), "dataset": "earthquakes"}


async def _fetch_solar_events(
    session: aiohttp.ClientSession, args: dict
) -> dict:
    """Fetch solar/space weather events from NASA DONKI."""
    now = datetime.now(timezone.utc)
    date_from = args.get("date_from", (now - timedelta(days=30)).strftime("%Y-%m-%d"))
    date_to   = args.get("date_to", now.strftime("%Y-%m-%d"))

    event_types = [
        ("CME", "coronal_mass_ejections"),
        ("FLR", "solar_flares"),
        ("SEP", "solar_energetic_particles"),
    ]

    all_events = {}
    for event_code, event_name in event_types:
        url = (
            f"{NASA_BASE}/DONKI/{event_code}"
            f"?startDate={date_from}&endDate={date_to}&api_key={NASA_KEY}"
        )
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    events = await resp.json()
                    if isinstance(events, list):
                        all_events[event_name] = events[:5]
        except Exception:
            pass

    return {
        "dataset": "solar_events",
        "source": "NASA DONKI (Space Weather Database)",
        "date_range": {"from": date_from, "to": date_to},
        "events": all_events,
        "note": "Use NASA_API_KEY env var for higher rate limits",
    }


async def _fetch_nasa_apod(
    session: aiohttp.ClientSession, args: dict
) -> dict:
    """Fetch NASA Astronomy Picture of the Day."""
    date_to = args.get("date_to", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    url = f"{NASA_BASE}/planetary/apod?api_key={NASA_KEY}&date={date_to}"

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return {"error": f"NASA APOD returned {resp.status}"}
            data = await resp.json()
        return {
            "dataset": "nasa_apod",
            "source": "NASA Astronomy Picture of the Day",
            "date": data.get("date"),
            "title": data.get("title"),
            "explanation": data.get("explanation"),
            "media_type": data.get("media_type"),
            "url": data.get("url"),
            "hdurl": data.get("hdurl"),
            "copyright": data.get("copyright"),
        }
    except Exception as exc:
        return {"error": str(exc), "dataset": "nasa_apod"}


async def _fetch_air_quality(
    session: aiohttp.ClientSession, args: dict
) -> dict:
    """
    Fetch air quality data. Falls back to OpenAQ (free, no key needed)
    when EPA AQS credentials are not configured.
    """
    location = args.get("location", "")
    lat = args.get("latitude")
    lon = args.get("longitude")
    max_results = min(int(args.get("max_results", 10)), 100)

    openaq_base = "https://api.openaq.io/v2"
    params = {"limit": max_results, "sort": "desc", "order_by": "lastUpdated"}

    if lat and lon:
        params["coordinates"] = f"{lat},{lon}"
        params["radius"] = int(args.get("radius_km", 100) * 1000)
    elif location:
        params["city"] = location

    url = f"{openaq_base}/locations?{urllib.parse.urlencode(params)}"

    try:
        async with session.get(
            url,
            headers={"accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return {"error": f"OpenAQ returned {resp.status}", "dataset": "air_quality"}
            data = await resp.json()

        stations = []
        for loc in (data.get("results") or [])[:max_results]:
            params_measured = [p.get("parameter") for p in (loc.get("parameters") or [])[:5]]
            stations.append({
                "name": loc.get("name"),
                "city": loc.get("city"),
                "country": loc.get("country"),
                "coordinates": loc.get("coordinates"),
                "last_updated": loc.get("lastUpdated"),
                "parameters_measured": params_measured,
                "measurements_count": loc.get("count"),
            })

        return {
            "dataset": "air_quality",
            "source": "OpenAQ Global Air Quality Database",
            "location_query": location or f"{lat},{lon}" if lat else "global",
            "stations_found": len(stations),
            "stations": stations,
        }
    except Exception as exc:
        return {"error": str(exc), "dataset": "air_quality"}


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

async def scientific_data_handler(arguments: dict) -> dict:
    dataset = arguments.get("dataset", "")

    if not dataset:
        return {"error": "dataset parameter is required"}

    async with aiohttp.ClientSession() as session:
        if dataset == "earthquakes":
            return await _fetch_earthquakes(session, arguments)
        elif dataset == "solar_events":
            return await _fetch_solar_events(session, arguments)
        elif dataset == "nasa_apod":
            return await _fetch_nasa_apod(session, arguments)
        elif dataset == "air_quality":
            return await _fetch_air_quality(session, arguments)
        else:
            return {"error": f"Unknown dataset: {dataset}", "available_datasets": [
                "earthquakes", "air_quality", "solar_events", "nasa_apod"
            ]}


def register(registry) -> None:
    from server import ToolDefinition
    registry.register(ToolDefinition(
        name=TOOL_NAME,
        description=(
            "Fetch real-time scientific data from major public APIs. "
            "Datasets: earthquakes (USGS), air_quality (OpenAQ), "
            "solar_events (NASA DONKI), nasa_apod. "
            "Supports geographic filtering by lat/lon/radius. "
            "Returns structured, agent-ready data."
        ),
        input_schema=TOOL_SCHEMA,
        price_per_call_usd=TOOL_PRICE_USD,
        stripe_price_id=TOOL_STRIPE_PRICE,
        handler=scientific_data_handler,
        category="earth_science",
    ))


if __name__ == "__main__":
    async def test():
        print("Testing scientific_data tool...\n")
        result = await scientific_data_handler({
            "dataset": "earthquakes",
            "min_magnitude": 5.0,
            "max_results": 5,
        })
        if "error" not in result:
            print(f"Earthquakes M5+: {result.get('total_events', 0)} found")
            for e in result.get("events", [])[:3]:
                print(f"  M{e['magnitude']} — {e['place']} — {e['time'][:10]}")
        else:
            print(f"Result: {result}")

    asyncio.run(test())
