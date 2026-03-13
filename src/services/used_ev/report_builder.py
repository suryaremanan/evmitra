"""
VoltSage — services/used_ev/report_builder.py
Assembles the final UsedEvReport dict from all agent outputs.
"""
import datetime

_MAX_QUESTIONS = 6

_RECOMMENDATION_MAP = {
    "WALK AWAY": {
        "action": "Walk Away",
        "detail": "Multiple serious red flags detected. Do not proceed with this transaction.",
        "icon": "🚨",
    },
    "HIGH RISK": {
        "action": "Proceed with Extreme Caution",
        "detail": (
            "Significant risk factors present. Get an independent EV inspection "
            "and battery health check before sending any money."
        ),
        "icon": "⚠️",
    },
    "CAUTION": {
        "action": "Negotiate & Verify",
        "detail": (
            "Some concerns found. Ask the seller to address the listed questions, "
            "request a battery diagnostic printout, and inspect in person before proceeding."
        ),
        "icon": "🔍",
    },
    "LOW RISK": {
        "action": "Looks Legitimate",
        "detail": "No major red flags detected. Get a pre-purchase EV inspection to confirm battery health.",
        "icon": "✅",
    },
}


def _questions_from_flags(flags: list, facts, battery) -> list[str]:
    questions: list[str] = []

    if not facts:
        return []

    if not facts.vin:
        questions.append("Can you provide the VIN so I can run a vehicle history report?")
    if any("duplic" in f.lower() for f in flags):
        questions.append("This listing appears identical to others — can you explain where else you've listed it?")
    if any("photo" in f.lower() for f in flags):
        questions.append("Can you send me new photos taken today, with your ID visible in the frame?")
    if any("identity" in f.lower() or "scam" in f.lower() for f in flags):
        questions.append("Can you verify your identity with a government-issued ID?")
    if any("below market" in f.lower() or "price is" in f.lower() for f in flags):
        questions.append("The price is significantly below market — what is the reason for the discount?")
    if any("battery" in f.lower() or "soh" in f.lower() or "degradation" in f.lower() for f in flags):
        questions.append("Can you share the official battery health report / diagnostic printout from a service center?")
    if any("recall" in f.lower() for f in flags):
        questions.append("Is the battery recall / service campaign completed? Can you show proof?")
    if any("odometer" in f.lower() for f in flags):
        questions.append("Can you share service records to verify the odometer reading?")

    # Always include these
    questions.append("Are you willing to meet at a neutral location for inspection before payment?")
    questions.append("Will you allow a pre-purchase inspection by an authorized EV service center?")

    return questions[:_MAX_QUESTIONS]


def build_report(
    facts,
    cross_check,
    market_data,
    battery,
    enrichment,
    risk_score,
    elapsed_seconds: float = 0.0,
    country: str = "india",
) -> dict:
    rec = _RECOMMENDATION_MAP.get(risk_score.band, _RECOMMENDATION_MAP["CAUTION"])
    questions = _questions_from_flags(risk_score.flags, facts, battery)

    vehicle_facts: dict = {}
    if facts:
        vehicle_facts = {
            "make": facts.make,
            "model": facts.model,
            "year": facts.year,
            "trim": facts.trim,
            "odometer_km": facts.odometer_km,
            "asking_price": facts.price,
            "seller_name": facts.seller_name,
            "seller_phone": facts.seller_phone,
            "seller_location": facts.seller_location,
            "vin": facts.vin,
            "listed_date": facts.listed_date,
            "listing_url": facts.listing_url,
            "claimed_range_km": facts.claimed_range_km,
        }

    market_comparison: dict = {}
    if market_data and not market_data.error:
        market_comparison = {
            "median_market_price": market_data.median_price,
            "low_price": market_data.low_price,
            "high_price": market_data.high_price,
            "listing_price": market_data.listing_price,
            "price_delta_pct": market_data.price_delta_pct,
            "market_verdict": market_data.market_verdict,
            "avg_odometer_km": market_data.avg_odometer_km,
            "sample_count": market_data.sample_count,
            "currency": market_data.currency,
            "comparables": market_data.comparables,
            "source_urls": market_data.source_urls,
        }

    battery_assessment: dict = {}
    if battery:
        battery_assessment = {
            "estimated_soh_pct": battery.estimated_soh_pct,
            "degradation_flag": battery.degradation_flag,
            "warranty_remaining": battery.warranty_remaining,
            "recall_found": battery.recall_found,
            "recall_details": battery.recall_details,
            "dc_charge_limited": battery.dc_charge_limited,
            "assessment": battery.assessment,
            "notes": battery.notes,
            "source_urls": battery.source_urls,
        }

    ev_specs: dict = {}
    if enrichment and not enrichment.error:
        ev_specs = {
            "spec_battery_kwh": enrichment.spec_battery_kwh,
            "spec_range_city_km": enrichment.spec_range_city_km,
            "spec_range_highway_km": enrichment.spec_range_highway_km,
            "spec_dc_kw": enrichment.spec_dc_kw,
            "warranty_months": enrichment.warranty_months,
            "known_issues": enrichment.known_issues,
            "source": enrichment.source,
        }

    evidence: dict = {}
    if cross_check:
        evidence["duplicate_listings"] = cross_check.duplicates
        evidence["photo_reuse"] = cross_check.image_reuses
        evidence["identity_flags"] = cross_check.identity_flags
        if cross_check.identity_source_url:
            evidence["identity_source_url"] = cross_check.identity_source_url

    return {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "country": country,
        "investigation_timing": {
            "elapsed_seconds": elapsed_seconds,
            "agents_run": 6,
            "parallel_agents": 4,
        },
        "fraud_risk": risk_score.fraud_risk,
        "ev_condition_risk": risk_score.ev_condition_risk,
        "overall_risk": risk_score.overall_risk,
        "risk_band": risk_score.band,
        "risk_band_color": risk_score.band_color,
        "recommendation": {
            "action": rec["action"],
            "detail": rec["detail"],
            "icon": rec["icon"],
        },
        "vehicle_facts": vehicle_facts,
        "ev_specs": ev_specs,
        "battery_assessment": battery_assessment,
        "market_comparison": market_comparison,
        "red_flags": risk_score.flags,
        "questions_to_ask": questions,
        "evidence": evidence,
        "penalty_breakdown": {
            "fraud": risk_score.fraud_penalties,
            "condition": risk_score.condition_penalties,
        },
    }
