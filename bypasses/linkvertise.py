"""
Linkvertise Bypass Engine
Reverse-engineered flow:
  1. Fetch the page → extract user_id, url_id, and CSRF/session tokens
  2. Hit their publisher API to get link data + a task token
  3. Complete the task handshake → get the paste/final URL
  4. Decode/follow any remaining redirects
"""

import httpx
import re
import json
import asyncio
from urllib.parse import urlparse, urljoin
from fastapi import HTTPException
from http_client import browser_headers, html_headers, get_client


LINKVERTISE_API = "https://publisher.linkvertise.com/api/v1"


def parse_lv_url(url: str) -> tuple[str, str]:
    """Extract user_id and url_id from a linkvertise URL."""
    # Formats:
    # https://linkvertise.com/{user_id}/{slug}
    # https://linkvertise.com/link/{user_id}/{url_id}
    path = urlparse(url).path.strip("/").split("/")

    if len(path) >= 2:
        user_id = path[0]
        url_id = path[1]
        if user_id == "link" and len(path) >= 3:
            user_id = path[1]
            url_id = path[2]
        return user_id, url_id

    raise HTTPException(status_code=400, detail="Could not parse Linkvertise URL structure.")


async def fetch_page_tokens(client: httpx.AsyncClient, url: str) -> dict:
    """Fetch the Linkvertise page and extract embedded JS config/tokens."""
    resp = await client.get(url, headers=html_headers(url))
    html = resp.text

    tokens = {}

    # Extract __NUXT__ or window.__LV__ style embedded data
    nuxt_match = re.search(r'window\.__NUXT__\s*=\s*(\{.+?\});', html, re.DOTALL)
    if nuxt_match:
        try:
            tokens["nuxt"] = json.loads(nuxt_match.group(1))
        except Exception:
            pass

    # Look for X-CSRF-TOKEN in meta tags
    csrf_match = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', html)
    if csrf_match:
        tokens["csrf"] = csrf_match.group(1)

    # Extract link ID from og:url or canonical
    og_match = re.search(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']', html)
    if og_match:
        tokens["og_url"] = og_match.group(1)

    # Try to grab any serialized state from the page (Linkvertise uses Vue/Nuxt)
    state_match = re.search(r'"link_id"\s*:\s*(\d+)', html)
    if state_match:
        tokens["link_id"] = state_match.group(1)

    user_id_match = re.search(r'"user_id"\s*:\s*(\d+)', html)
    if user_id_match:
        tokens["user_id"] = user_id_match.group(1)

    return tokens


async def get_link_data(client: httpx.AsyncClient, user_id: str, url_id: str) -> dict:
    """Call Linkvertise publisher API to get link metadata + task info."""
    api_url = f"{LINKVERTISE_API}/redirect/link/{user_id}/{url_id}"
    headers = browser_headers(
        referer=f"https://linkvertise.com/{user_id}/{url_id}",
        origin="https://linkvertise.com"
    )
    headers["X-Requested-With"] = "XMLHttpRequest"

    resp = await client.get(api_url, headers=headers)

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Linkvertise link not found or expired.")
    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"Linkvertise API error: {resp.status_code}")

    try:
        return resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Linkvertise API returned non-JSON response.")


async def complete_link_task(client: httpx.AsyncClient, user_id: str, url_id: str, link_data: dict) -> str | None:
    """
    Try to complete the ad task and get the target URL.
    Linkvertise requires completing an 'ad interaction' task.
    We simulate the required API calls to mark the task done.
    """
    # Get the target from link_data if it's already exposed
    # (some link types expose it directly for non-JS clients)
    data = link_data.get("data", link_data)

    # Direct URL in response
    for key in ("target", "url", "link", "destination", "redirect_url", "final_url"):
        val = data.get(key)
        if val and val.startswith("http"):
            return val

    # Try nested structures
    if isinstance(data.get("link"), dict):
        for key in ("url", "target", "destination"):
            val = data["link"].get(key)
            if val and val.startswith("http"):
                return val

    # Attempt the task completion endpoint
    task_token = data.get("token") or data.get("task_token") or data.get("t")
    if task_token:
        task_url = f"{LINKVERTISE_API}/redirect/link/{user_id}/{url_id}/complete"
        headers = browser_headers(
            referer=f"https://linkvertise.com/{user_id}/{url_id}",
            origin="https://linkvertise.com"
        )
        payload = {"token": task_token}
        resp = await client.post(task_url, json=payload, headers=headers)
        if resp.is_success:
            try:
                result = resp.json()
                result_data = result.get("data", result)
                for key in ("target", "url", "link", "destination"):
                    val = result_data.get(key)
                    if val and val.startswith("http"):
                        return val
            except Exception:
                pass

    return None


async def follow_shortlink(client: httpx.AsyncClient, url: str) -> str:
    """Follow any redirect chain and return the final URL."""
    try:
        resp = await client.get(url, headers=html_headers(url))
        return str(resp.url)
    except Exception:
        return url


async def bypass_linkvertise(url: str) -> str:
    """
    Full Linkvertise bypass pipeline with fallback strategies.
    """
    async with await get_client() as client:
        user_id, url_id = parse_lv_url(url)

        # Strategy 1: Hit the API directly
        link_data = await get_link_data(client, user_id, url_id)
        result = await complete_link_task(client, user_id, url_id, link_data)

        if result:
            # Follow any redirect chains (bit.ly, etc.)
            final = await follow_shortlink(client, result)
            return final

        # Strategy 2: Fetch the page and try to extract from embedded state
        page_tokens = await fetch_page_tokens(client, url)

        # Use any link_id found in the page
        page_link_id = page_tokens.get("link_id")
        page_user_id = page_tokens.get("user_id") or user_id

        if page_link_id:
            link_data2 = await get_link_data(client, page_user_id, page_link_id)
            result2 = await complete_link_task(client, page_user_id, page_link_id, link_data2)
            if result2:
                return await follow_shortlink(client, result2)

        # Strategy 3: Try alternate API path
        alt_url = f"{LINKVERTISE_API}/link/{user_id}/{url_id}"
        headers = browser_headers(referer=url, origin="https://linkvertise.com")
        try:
            alt_resp = await client.get(alt_url, headers=headers)
            if alt_resp.is_success:
                alt_data = alt_resp.json()
                result3 = await complete_link_task(client, user_id, url_id, alt_data)
                if result3:
                    return await follow_shortlink(client, result3)
        except Exception:
            pass

    raise HTTPException(
        status_code=502,
        detail="All Linkvertise bypass strategies failed. Link may be heavily protected or expired."
    )
