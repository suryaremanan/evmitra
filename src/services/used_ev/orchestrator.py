"""
VoltSage — services/used_ev/orchestrator.py
Orchestrates all Used EV due-diligence agents.
Uses an emit() callback pattern — no global run store.
Every SSE event goes through emit(); the router bridges emit() to an asyncio.Queue.
"""
import asyncio
import time
from typing import Awaitable, Callable

from core.config import logger, normalize_country

from .battery_health import assess_battery
from .cross_checker import cross_check
from .ev_enrichment import get_ev_enrichment
from .listing_extractor import extract_listing
from .market_sanity import check_market
from .models import BatteryHealth, CrossCheckResult, EvEnrichment, MarketData, UsedEvRequest
from .report_builder import build_report
from .scorer import score_risk

EmitFn = Callable[[dict], Awaitable[None]]


async def investigate(req: UsedEvRequest, emit: EmitFn) -> None:
    """
    Full Used EV investigation pipeline.
    Emits SSE-style event dicts via emit().
    The router wraps emit() to push into an asyncio.Queue feeding StreamingResponse.
    """
    country = normalize_country(req.country)
    start_time = time.monotonic()

    try:
        # ── Stage 1: Extract listing ──────────────────────────────────────────
        await emit({
            "type": "STAGE",
            "stage": 1,
            "message": "Opening listing and extracting vehicle details…",
        })

        facts = await extract_listing(
            listing_url=req.listing_url,
            vin_hint=req.vin_hint,
            phone_hint=req.phone_hint,
        )

        if facts.error:
            await emit({"type": "WARNING", "message": f"Listing extraction issue: {facts.error}"})
        else:
            odo_str = f"{facts.odometer_km:,} km" if facts.odometer_km else "unknown km"
            await emit({
                "type": "AGENT_COMPLETE",
                "agent": "listing",
                "message": (
                    f"Listing extracted: {facts.year} {facts.make} {facts.model}, "
                    f"{facts.price}, {odo_str}"
                ),
            })

        # ── Stage 2: Parallel agents ──────────────────────────────────────────
        await emit({
            "type": "STAGE",
            "stage": 2,
            "message": (
                "Deploying 4 agents in parallel — "
                "duplicate scan, reverse image search, market pricing, EV specs…"
            ),
        })

        _results = await asyncio.gather(
            cross_check(facts, country=country),
            check_market(facts, country=country),
            assess_battery(facts),
            get_ev_enrichment(facts.make, facts.model, facts.year, country),
            return_exceptions=True,
        )

        cross_result   = _results[0] if not isinstance(_results[0], Exception) else CrossCheckResult()
        market_result  = _results[1] if not isinstance(_results[1], Exception) else MarketData(error=str(_results[1]))
        battery_result = _results[2] if not isinstance(_results[2], Exception) else BatteryHealth(assessment="UNKNOWN")
        enrichment     = _results[3] if not isinstance(_results[3], Exception) else EvEnrichment()

        # Cross-check summary
        dup_n = len(cross_result.duplicates)
        img_n = len(cross_result.image_reuses)
        id_n  = len(cross_result.identity_flags)
        await emit({
            "type": "AGENT_COMPLETE",
            "agent": "cross_check",
            "message": (
                f"Cross-check complete: {dup_n} verified duplicate(s) with URLs, "
                f"{img_n} confirmed photo reuse(s), {id_n} identity flag(s)"
            ),
        })

        if market_result and not market_result.error:
            delta_str = (
                f"{'+' if (market_result.price_delta_pct or 0) >= 0 else ''}"
                f"{market_result.price_delta_pct or 0:.1f}%"
            )
            await emit({
                "type": "AGENT_COMPLETE",
                "agent": "market",
                "message": (
                    f"Market data: median {market_result.currency} "
                    f"{market_result.median_price:,.0f} "
                    f"({delta_str} vs listing)"
                ) if market_result.median_price else "Market data retrieved",
            })

        if battery_result and not battery_result.error:
            soh_str = (
                f"~{battery_result.estimated_soh_pct}%"
                if battery_result.estimated_soh_pct is not None
                else "unknown"
            )
            await emit({
                "type": "AGENT_COMPLETE",
                "agent": "battery",
                "message": (
                    f"Battery health: estimated SoH {soh_str} "
                    f"— {battery_result.assessment}"
                    + (", RECALL FOUND" if battery_result.recall_found else "")
                ),
            })

        if enrichment and not enrichment.error:
            specs_str = (
                f"{enrichment.spec_battery_kwh} kWh, "
                f"{enrichment.spec_range_city_km} km range"
                if enrichment.spec_battery_kwh and enrichment.spec_range_city_km
                else "specs retrieved"
            )
            await emit({
                "type": "AGENT_COMPLETE",
                "agent": "ev_specs",
                "message": f"EV specs ({enrichment.source}): {specs_str}",
            })

        # ── Stage 3: Score & report ───────────────────────────────────────────
        await emit({
            "type": "STAGE",
            "stage": 3,
            "message": "Calculating risk score and generating report…",
        })

        elapsed_seconds = round(time.monotonic() - start_time, 1)

        risk = score_risk(facts, cross_result, market_result, battery_result, enrichment)
        report = build_report(
            facts=facts,
            cross_check=cross_result,
            market_data=market_result,
            battery=battery_result,
            enrichment=enrichment,
            risk_score=risk,
            elapsed_seconds=elapsed_seconds,
            country=country,
        )

        await emit({
            "type": "COMPLETE",
            "report": report,
            "elapsed_seconds": elapsed_seconds,
        })

    except Exception as exc:
        logger.exception("Used EV investigation failed")
        await emit({"type": "ERROR", "message": str(exc)})
