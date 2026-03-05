"""
EV Mitra — routers/chargers.py
Legacy GET /chargers/stream — thin SSE proxy over TinyFish.
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import requests as req

from core.config import (
    TINYFISH_API_KEY, TINYFISH_BASE_URL, logger,
)
from services.tinyfish_service import tinyfish_cb

router = APIRouter()


@router.get("/chargers/stream")
async def stream_chargers(city: str = "Nagpur"):
    """
    Streams TinyFish scraping events as Server-Sent Events (SSE).
    Each event is one of: PROGRESS, COMPLETE, ERROR.
    """
    city = city.strip().capitalize()

    payload = {
        "url": f"https://www.statiq.in/charging-stations/{city.lower()}",
        "goal": f"""
List all EV charging stations on this page for {city}, India.
Return JSON exactly like this:
{{
  "city": "{city}",
  "network": "Statiq",
  "stations": [
    {{
      "name": "station name",
      "address": "full address with area",
      "connector_types": ["DC", "AC"],
      "power_kw": 50,
      "status": "available"
    }}
  ],
  "total_found": 0
}}
If no stations found for {city}, return total_found: 0 and empty stations array. Be honest.
        """,
        "browser_profile": "lite",
    }

    def generate():
        if tinyfish_cb.is_open:
            yield f"data: {json.dumps({'type': 'ERROR', 'message': f'TinyFish unavailable: {tinyfish_cb.status}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'status': 'error'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'STATUS', 'message': f'Connecting to TinyFish for {city}...'})}\n\n"

        try:
            with req.post(
                TINYFISH_BASE_URL,
                json=payload,
                headers={
                    "X-API-Key": TINYFISH_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                stream=True,
                timeout=180,
            ) as resp:
                if resp.status_code != 200:
                    try:
                        err_msg = (resp.json().get("error") or {}).get("message") or f"HTTP {resp.status_code}"
                    except Exception:
                        err_msg = f"HTTP {resp.status_code}"
                    yield f"data: {json.dumps({'type': 'ERROR', 'message': f'TinyFish error: {err_msg}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'status': 'error'})}\n\n"
                    return

                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                        event_type = event.get("type", "")

                        if event_type == "COMPLETE":
                            charger_data = event.get("resultJson", {"stations": [], "total_found": 0})
                            if isinstance(charger_data, str):
                                try:
                                    charger_data = json.loads(charger_data)
                                except Exception:
                                    charger_data = {"stations": [], "total_found": 0}
                            yield f"data: {json.dumps({'type': 'COMPLETE', 'data': charger_data})}\n\n"
                            yield f"data: {json.dumps({'type': 'done', 'status': 'complete'})}\n\n"
                            return
                        elif event_type == "ERROR":
                            yield f"data: {json.dumps({'type': 'ERROR', 'message': event.get('message', 'Unknown error')})}\n\n"
                            yield f"data: {json.dumps({'type': 'done', 'status': 'error'})}\n\n"
                            return
                        else:
                            msg = event.get("message") or event.get("step") or event_type
                            yield f"data: {json.dumps({'type': 'PROGRESS', 'step': event_type, 'message': str(msg)})}\n\n"

                    except json.JSONDecodeError:
                        continue

        except req.Timeout:
            yield f"data: {json.dumps({'type': 'ERROR', 'message': 'TinyFish timed out after 180s'})}\n\n"
        except Exception as e:
            logger.exception("chargers/stream failed")
            yield f"data: {json.dumps({'type': 'ERROR', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'status': 'error'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
