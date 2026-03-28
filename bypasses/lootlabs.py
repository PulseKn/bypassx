"""
Lootlabs / Loot-Link Bypass Engine
Flow:
  1. GET the page to grab the task ID and CSRF token
  2. POST /api/v1/link/start with the task ID
  3. Poll /api/v1/link/check until completed
  4. GET the final URL from the response
"""

import httpx
import re
import json
import asyncio
from fastapi import HTTPException
from http_client import browser_headers, html_headers, get_client


LOOTLABS_BASE = "https://loot-link.com"
LOOTLABS_API  = f"{LOOTLABS_BASE}/api/v1"


def extract_task_id(html: str) -> str | None:
    patterns = [
        r'task_id\s*[=:]\s*["\']?(\w+)["\']?',
        r'["\']taskId["\']\s*:\s*["\'](\w+)["\']',
        r'data-task-id=["\'](\w+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def extract_csrf(html: str) -> str | None:
    m = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']', html)
    return m.group(1) if m else None


async def start_task(client: httpx.AsyncClient, task_id: str, csrf: str, url: str) -> dict:
    headers = browser_headers(referer=url, origin=LOOTLABS_BASE)
    if csrf:
        headers["X-CSRF-TOKEN"] = csrf
    headers["Content-Type"] = "application/json"

    resp = await client.post(
        f"{LOOTLABS_API}/link/start",
        json={"task_id": task_id},
        headers=headers
    )
    try:
        return resp.json()
    except Exception:
        return {}


async def poll_task(client: httpx.AsyncClient, task_id: str, session_token: str, csrf: str, url: str, max_attempts: int = 8) -> str | None:
    headers = browser_headers(referer=url, origin=LOOTLABS_BASE)
    if csrf:
        headers["X-CSRF-TOKEN"] = csrf
    if session_token:
        headers["X-Session-Token"] = session_token

    for attempt in range(max_attempts):
        await asyncio.sleep(1.5)
        resp = await client.post(
            f"{LOOTLABS_API}/link/check",
            json={"task_id": task_id},
            headers=headers
        )
        try:
            data = resp.json()
        except Exception:
            continue

        status = data.get("status") or data.get("state")
        if status in ("completed", "done", "success", True, 1):
            return (
                data.get("url") or
                data.get("destination") or
                data.get("redirect") or
                data.get("link")
            )
        if status in ("failed", "error", "expired"):
            break

    return None


async def bypass_lootlabs(url: str) -> str:
    async with await get_client() as client:
        # Step 1 — fetch page
        resp = await client.get(url, headers=html_headers(url))
        html = resp.text

        task_id = extract_task_id(html)
        csrf = extract_csrf(html)

        if not task_id:
            raise HTTPException(status_code=502, detail="Could not extract Lootlabs task ID from page.")

        # Step 2 — start task
        start_data = await start_task(client, task_id, csrf or "", url)
        session_token = start_data.get("token") or start_data.get("session_token") or ""

        # Step 3 — poll for completion
        result = await poll_task(client, task_id, session_token, csrf or "", url)

        if result and result.startswith("http"):
            return result

    raise HTTPException(status_code=502, detail="Lootlabs bypass timed out or failed.")
