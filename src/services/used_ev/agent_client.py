"""
VoltSage — services/used_ev/agent_client.py
Sync TinyFish SSE client (requests-based, matching tinyfish_service.py pattern).
Async wrapper uses asyncio.to_thread for parallel fan-out.
"""
import asyncio
import json
from typing import Optional

import requests as req

from core.config import TINYFISH_API_KEY, TINYFISH_BASE_URL, TINYFISH_DEFAULT_TIMEOUT, logger


def run_agent(
    url: str,
    goal: str,
    label: str,
    profile: str = "stealth",
    timeout: Optional[int] = TINYFISH_DEFAULT_TIMEOUT,
) -> dict:
    """
    Sync TinyFish SSE call — returns parsed resultJson dict or {"error": ...}.
    Never raises; callers check result.get("error").
    Payload matches tinyfish_service.py exactly: {url, goal, browser_profile}.
    """
    if not TINYFISH_API_KEY:
        return {"error": "TINYFISH_API_KEY is not set"}

    headers = {
        "X-API-Key": TINYFISH_API_KEY,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    try:
        with req.post(
            TINYFISH_BASE_URL,
            json={"url": url, "goal": goal, "browser_profile": profile},
            headers=headers,
            stream=True,
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                try:
                    err_body = resp.json()
                    err_msg = (err_body.get("error") or {}).get("message") or str(err_body)
                except Exception:
                    err_msg = resp.text[:200] or f"HTTP {resp.status_code}"
                logger.warning("[%s] TinyFish HTTP %d: %s", label, resp.status_code, err_msg)
                return {"error": f"HTTP {resp.status_code}: {err_msg}"}

            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                    etype = event.get("type", "")
                    if etype == "COMPLETE":
                        result = event.get("resultJson") or {}
                        if isinstance(result, str):
                            result = json.loads(result)
                        return result if isinstance(result, dict) else {}
                    elif etype == "ERROR":
                        msg = event.get("message", "Agent error")
                        logger.warning("[%s] TinyFish error event: %s", label, msg)
                        return {"error": msg}
                except json.JSONDecodeError:
                    continue

    except (req.exceptions.Timeout, req.exceptions.ConnectionError):
        pass  # expected with short deadlines
    except Exception as exc:
        if "timed out" not in str(exc).lower() and "timeout" not in str(exc).lower():
            logger.warning("[%s] TinyFish call failed: %s", label, exc)

    return {"error": f"{label}: agent completed without returning data"}


async def run_agent_async(
    url: str,
    goal: str,
    label: str,
    profile: str = "stealth",
    timeout: Optional[int] = TINYFISH_DEFAULT_TIMEOUT,
) -> dict:
    """Async wrapper — runs sync run_agent() in a thread pool."""
    return await asyncio.to_thread(
        run_agent, url, goal, label, profile, timeout
    )
