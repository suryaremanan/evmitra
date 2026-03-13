"""
VoltSage — routers/used_ev.py
POST /used-ev/stream  — SSE endpoint for Used EV due-diligence investigation.
Matches VoltSage's existing SSE style from verdict.py.
"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.config import logger
from services.used_ev.models import UsedEvRequest
from services.used_ev.orchestrator import investigate

router = APIRouter()

# ALL_DATA injection (unused for now — ev_enrichment.py calls set_all_data separately)
_ALL_DATA: dict = {}


def set_all_data(data: dict) -> None:
    global _ALL_DATA
    _ALL_DATA = data
    from services.used_ev.ev_enrichment import set_all_data as _ev_set
    _ev_set(data)


@router.post("/used-ev/stream")
async def used_ev_stream(req: UsedEvRequest):
    """
    Stream a Used EV investigation as Server-Sent Events.

    Request body:
        listing_url  — URL of the used EV listing (required)
        country      — e.g. "india", "usa", "uk" (default: "india")
        city         — city hint for market search (optional)
        vin_hint     — known VIN to cross-check (optional)
        phone_hint   — known seller phone (optional)

    SSE events:
        STAGE          — investigation stage update
        PROGRESS       — per-agent progress messages
        AGENT_COMPLETE — single agent done summary
        WARNING        — non-fatal warning
        COMPLETE       — investigation done, report in `report` field
        ERROR          — fatal error
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def run() -> None:
        try:
            await investigate(req, emit)
        except Exception as exc:
            logger.exception("used-ev/stream: unhandled error")
            await queue.put({"type": "ERROR", "message": str(exc)})
        finally:
            await queue.put(None)  # sentinel

    asyncio.create_task(run())

    async def event_stream():
        while True:
            event = await queue.get()
            if event is None:
                return
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") in ("COMPLETE", "ERROR"):
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
