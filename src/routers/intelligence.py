"""
EV Mitra — routers/intelligence.py
/intelligence-report — B2B competitive charger gap analysis (SSE).
"""

import json
import queue as _queue
import threading
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import normalize_city, normalize_country, market_region_for_city, logger
from services.charger_service import provider_sources_for_city
from services.tinyfish_service import tinyfish_call

router = APIRouter()


class IntelligenceRequest(BaseModel):
    country: str = "India"
    city: str = "Bangalore"
    report_type: str = "charger_gap_analysis"


@router.post("/intelligence-report")
def intelligence_report(req: IntelligenceRequest):
    city = normalize_city(req.city)
    country = normalize_country(req.country)

    def goal(network):
        return f"""Find all EV charging stations for {city}, {country.title()} on this page.
Return JSON:
{{
  "city": "{city}",
  "country": "{country}",
  "network": "{network}",
  "stations": [
    {{
      "name": "station name",
      "address": "full address",
      "connector_types": ["DC", "AC"],
      "power_kw": 50
    }}
  ],
  "total_found": 0
}}
Be honest. Return total_found: 0 if none found."""

    sources = provider_sources_for_city(city, country)

    def generate():
        yield f"data: {json.dumps({'type': 'SCANNING', 'message': f'Scanning {len(sources)} networks for {city}, {country.title()} in parallel...'})}\n\n"

        result_q = _queue.Queue()

        def scrape(source):
            data = tinyfish_call(source["url"], goal(source["name"]), source["profile"], timeout=110)
            result_q.put((source["name"], data))

        threads = [threading.Thread(target=scrape, args=(s,), daemon=True) for s in sources]
        for t in threads:
            t.start()

        network_data = {}
        for _ in sources:
            name, data = result_q.get()
            network_data[name] = data
            n = len(data.get("stations") or [])
            yield f"data: {json.dumps({'type': 'NETWORK_DONE', 'network': name, 'stations_found': n})}\n\n"

        for t in threads:
            t.join()

        breakdown = {}
        for name, data in network_data.items():
            stations  = data.get("stations") or []
            dc        = [s for s in stations if "DC" in (s.get("connector_types") or [])]
            fast      = [s for s in dc if (s.get("power_kw") or 0) >= 50]
            breakdown[name] = {
                "total":             len(stations),
                "dc_chargers":       len(dc),
                "fast_dc_50kw_plus": len(fast),
                "max_power_kw":      max(((s.get("power_kw") or 0) for s in stations), default=0),
            }

        all_stations = [s for d in network_data.values() for s in (d.get("stations") or [])]
        total      = len(all_stations)
        dc_total   = sum(b["dc_chargers"]       for b in breakdown.values())
        fast_total = sum(b["fast_dc_50kw_plus"] for b in breakdown.values())

        dominant = max(breakdown, key=lambda k: breakdown[k]["dc_chargers"]) if breakdown else "Unknown"
        dom_dc   = breakdown.get(dominant, {}).get("dc_chargers", 0)
        dom_pct  = round(dom_dc / max(dc_total, 1) * 100)

        gaps = []
        if fast_total < 5:
            gaps.append(f"Only {fast_total} fast chargers (>=50kW) across all networks — insufficient for highway-adjacent EV use.")
        if dom_pct > 60:
            gaps.append(f"{dominant} controls {dom_pct}% of DC capacity — single-network dependency creates reliability risk for fleet operators.")
        if dc_total < total * 0.5:
            gaps.append(f"Only {dc_total}/{total} stations offer DC fast charging — AC-heavy coverage limits quick top-ups on busy days.")
        if not gaps:
            gaps.append("Healthy multi-network redundancy detected — strong coverage foundation for EV adoption.")

        shortfall = max(0, 10 - fast_total)
        opportunity = (
            f"{'High-growth opportunity' if total < 20 else 'Competitive market'}: "
            f"{city} needs {shortfall} more 50kW+ chargers to meet projected demand for {total * 3}+ EVs."
            if shortfall > 0 else
            f"{city} has solid fast-DC infrastructure. Expansion opportunity is in AC home-charging support and reliability monitoring."
        )

        payload = {
            "type":                        "COMPLETE",
            "country":                     country,
            "city":                        city,
            "report_type":                 req.report_type,
            "total_stations_all_networks": total,
            "dc_fast_chargers":            dc_total,
            "fast_50kw_plus":              fast_total,
            "network_breakdown":           breakdown,
            "dominant_network":            dominant,
            "dominant_dc_share_pct":       dom_pct,
            "gaps_and_risks":              gaps,
            "opportunity":                 opportunity,
            "data_freshness": {
                "source_type": "live" if any((network_data[k].get("stations") or []) for k in network_data)
                               else "static_fallback",
                "scraped_at":  datetime.now(timezone.utc).isoformat(),
            },
        }
        yield f"data: {json.dumps(payload)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'status': 'complete'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
