"""
VoltSage — services/used_ev/cross_checker.py
Agents 2a/2b/2c: Duplicate scan, photo reverse-search, seller identity check.
All three run in parallel via asyncio.to_thread. Only URL-backed findings accepted.
"""
import asyncio

from .agent_client import run_agent_async
from .models import CrossCheckResult, ListingFacts


def _dup_goal(vin: str, phone: str, year: str, make: str, model: str) -> str:
    return f"""\
You are a fraud investigator. Search for duplicate or fraudulent used EV listings.

Target: {year} {make} {model}
VIN: "{vin or 'not provided'}"
Seller phone: "{phone or 'not provided'}"

Search steps — run ALL that apply:
1. Google → "{year} {make} {model} used for sale {vin or ''}" — check multiple results
2. If VIN provided: Google → "{vin}" used car OR EV for sale
3. If phone provided: Google → "{phone}" used car OR EV sale
4. Search OLX / Cars24 / Spinny / CarDekho / similar marketplace for the same VIN or phone

A listing is a DUPLICATE if it shares the same VIN, same phone, or nearly identical
photos/description across different sellers or platforms. Do NOT flag the same listing
URL appearing in multiple search results.

CRITICAL ACCURACY RULES:
- MUST click through to each potential duplicate and confirm the page exists
- ONLY include a result if you have navigated to the EXACT URL from your browser address bar
- "url" MUST start with "https://" and be the real URL you visited
- Empty array [] is the CORRECT response when no confirmed duplicates exist
- Never fabricate, guess, or approximate a URL

Return a JSON array (empty [] if nothing confirmed):
[
  {{
    "platform": "Cars24",
    "url": "https://www.cars24.com/buy-used-tata-nexon-...",
    "price": "₹11,50,000",
    "date": "Feb 2025",
    "seller": "Rahul",
    "note": "same VIN"
  }}
]"""


def _img_goal(photo_url: str) -> str:
    return f"""\
Perform a reverse image search to find if this EV listing photo appears elsewhere.

Photo URL: {photo_url}

Steps:
1. Go to https://lens.google.com/uploadbyurl?url={photo_url}
2. Review ALL results — identify pages OTHER than the original listing showing this image
3. If Google Lens returns no results, try: https://tineye.com/search?url={photo_url}
4. Click through to each match to confirm it is a car listing, not a press photo

Exclude: manufacturer press images, review articles, image-hosting sites with no
car-sale context. Only report results indicating the photo was reused in a different
car listing.

CRITICAL ACCURACY RULES:
- MUST click through to each result and confirm the URL in your browser address bar
- "source_url" MUST start with "https://" — the real URL you visited
- If you cannot navigate to the matching page, do NOT include it
- Empty array [] is the CORRECT response when no confirmed matches exist

Return a JSON array ([] if no confirmed matches):
[
  {{
    "page_title": "2021 Tata Nexon EV — Cars24 listing",
    "source_url": "https://www.cars24.com/buy-used-...",
    "match_type": "exact"
  }}
]"""


def _identity_goal(phone: str, name: str, country: str) -> str:
    return f"""\
Investigate this EV seller for fraud and scam signals.

Seller phone: "{phone or 'not provided'}"
Seller name: "{name or 'unknown'}"
Country: {country}

Steps:
1. Google → "{phone}" car scam fraud — read the first 5 results carefully
2. Google → "{phone}" "{name}" vehicle fraud OR cheating
3. If a scam-reporting site appears (ScamNumbers, ComplaintsBoard, JustDial fraud,
   Truecaller reports, Whoscall, 800notes) — click through and read the reports
4. Note any scam alerts, alternate names, or warning patterns for this number

CRITICAL ACCURACY RULES:
- Only report comments you ACTUALLY READ on pages you visited
- Do not guess or fabricate scam reports
- "source_url" MUST be the exact URL you visited

Return JSON:
{{
  "scam_reports": ["exact text or close paraphrase of each distinct report found"],
  "linked_names": ["other names you saw associated with this phone"],
  "warning_sites": ["site name: brief description of what was found"],
  "source_url": "https://...",
  "clean": true
}}

Set "clean": false if ANY warnings were found. "clean": true only when zero negative reports exist."""


def _normalize_list(result, *keys) -> list:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in keys:
            val = result.get(key)
            if isinstance(val, list):
                return val
    return []


async def cross_check(
    facts: ListingFacts,
    country: str = "india",
) -> CrossCheckResult:
    """
    Run duplicate-check, photo reverse-search, and identity-check in parallel.
    Each sync agent call runs in a thread via run_agent_async (asyncio.to_thread).
    Only URL-backed findings are accepted.
    """
    vin = facts.vin or ""
    phone = facts.seller_phone or ""
    name = facts.seller_name or "unknown"
    photo_url = facts.photo_urls[0] if facts.photo_urls else ""

    coros = [
        run_agent_async(
            "https://www.google.com",
            _dup_goal(vin, phone, facts.year, facts.make, facts.model),
            "Duplicate Check",
            profile="stealth",
            timeout=120,
        ),
        run_agent_async(
            "https://lens.google.com",
            _img_goal(photo_url),
            "Photo Check",
            profile="stealth",
            timeout=100,
        ) if photo_url else asyncio.sleep(0, result={}),
        run_agent_async(
            "https://www.google.com",
            _identity_goal(phone, name, country),
            "Identity Check",
            profile="lite",
            timeout=100,
        ),
    ]

    results = await asyncio.gather(*coros, return_exceptions=True)
    dup_raw = results[0] if not isinstance(results[0], Exception) else {}
    img_raw = results[1] if not isinstance(results[1], Exception) else {}
    id_raw  = results[2] if not isinstance(results[2], Exception) else {}

    # Only accept findings backed by a real navigated URL
    duplicates = [
        d for d in _normalize_list(dup_raw, "duplicates", "listings", "results", "data")
        if isinstance(d, dict) and str(d.get("url", "")).startswith("http")
    ]
    image_reuses = [
        r for r in _normalize_list(img_raw, "matches", "results", "pages", "data")
        if isinstance(r, dict) and str(r.get("source_url", "")).startswith("http")
    ]

    identity_flags: list[str] = []
    identity_source_url = ""
    if isinstance(id_raw, dict) and not id_raw.get("clean", True):
        for report in id_raw.get("scam_reports", []):
            if report:
                identity_flags.append(f"Scam report: {report}")
        linked = [n for n in id_raw.get("linked_names", []) if n]
        if len(linked) > 1:
            identity_flags.append(
                f"Phone linked to multiple names: {', '.join(str(x) for x in linked)}"
            )
        for site in id_raw.get("warning_sites", []):
            if site:
                identity_flags.append(f"Listed on warning site: {site}")
        identity_source_url = id_raw.get("source_url", "")

    return CrossCheckResult(
        duplicates=[d for d in duplicates if isinstance(d, dict)],
        image_reuses=[r for r in image_reuses if isinstance(r, dict)],
        identity_flags=identity_flags,
        identity_source_url=identity_source_url,
    )
