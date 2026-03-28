"""
Work.ink / Delta Bypass Engine
Flow:
  1. GET the page, extract the link token and verify URL
  2. POST to their verify endpoint
  3. Grab the destination URL from the response
"""

import httpx
import re
from fastapi import HTTPException
from http_client import browser_headers, html_headers, get_client


WORKINK_BASE = "https://work.ink"


def extract_workink_id(url: str) -> str:
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else ""


async def fetch_workink_data(client: httpx.AsyncClient, url: str) -> dict:
    """Fetch the work.ink page and pull out the embedded link data."""
    resp = await client.get(url, headers=html_headers(url))
    html = resp.text

    token = None
    link_id = None

    # Try to extract the token from script tags
    token_match = re.search(r'["\']token["\']\s*:\s*["\']([^"\']+)["\']', html)
    if token_match:
        token = token_match.group(1)

    # Extract the link ID from the page data
    id_match = re.search(r'["\']id["\']\s*:\s*["\']?(\w+)["\']?', html)
    if id_match:
        link_id = id_match.group(1)

    # Also check for next.js __NEXT_DATA__ or similar
    next_match = re.search(r'id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>', html, re.DOTALL)
    if next_match:
        try:
            import json
            nd = json.loads(next_match.group(1))
            props = nd.get("props", {}).get("pageProps", {})
            token = token or props.get("token") or props.get("linkToken")
            link_id = link_id or props.get("id") or props.get("linkId")
        except Exception:
            pass

    return {"token": token, "link_id": link_id, "html": html}


async def verify_workink(client: httpx.AsyncClient, url: str, token: str, link_id: str) -> str | None:
    """POST to the work.ink verify endpoint."""
    verify_url = f"{WORKINK_BASE}/api/verify"
    headers = browser_headers(referer=url, origin=WORKINK_BASE)
    payload = {"token": token, "id": link_id}

    resp = await client.post(verify_url, json=payload, headers=headers)
    if not resp.is_success:
        return None

    try:
        data = resp.json()
        return (
            data.get("url") or
            data.get("destination") or
            data.get("redirect") or
            data.get("link")
        )
    except Exception:
        return None


async def bypass_workink(url: str) -> str:
    async with await get_client() as client:
        data = await fetch_workink_data(client, url)

        token = data.get("token")
        link_id = data.get("link_id")

        if token and link_id:
            result = await verify_workink(client, url, token, link_id)
            if result and result.startswith("http"):
                return result

        # Fallback: try following all redirects directly
        try:
            resp = await client.get(url, headers=html_headers(url))
            final = str(resp.url)
            if final != url:
                return final
        except Exception:
            pass

    raise HTTPException(status_code=502, detail="Work.ink bypass failed. Link may be unsupported or changed.")
