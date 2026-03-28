# BypassX Engine v2

Custom ad-link bypass API — no third-party services. Built with FastAPI + httpx.

## Project Structure

```
bypassx/
├── main.py               # FastAPI app, routing, rate limiting
├── cache.py              # In-memory TTL cache
├── http_client.py        # Shared async HTTP client + browser headers
├── bypasses/
│   ├── linkvertise.py    # Linkvertise bypass engine (3 strategies)
│   ├── workink.py        # Work.ink / Delta bypass engine
│   └── lootlabs.py       # Lootlabs / Loot-Link bypass engine
├── requirements.txt
└── render.yaml
```

## Run Locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## Deploy on Render

1. Push this folder to a GitHub repo
2. Go to render.com → New → Web Service
3. Connect the repo — `render.yaml` will auto-configure everything
4. Done. Your API is live at `https://bypassx-engine.onrender.com`

## API Usage

### Bypass a link
```
GET /bypass?url=LINK&type=auto
```

**Parameters:**
| Param | Description |
|-------|-------------|
| `url` | The ad link to bypass |
| `type` | `auto` (default), `linkvertise`, `workink`, `lootlabs` |

**Response:**
```json
{
  "success": true,
  "cached": false,
  "type": "linkvertise",
  "original": "https://linkvertise.com/...",
  "result": "https://actual-destination.com/file",
  "timestamp": 1711500000
}
```

### Other endpoints
```
GET /         → Info + supported types
GET /health   → Health check
GET /stats    → Cache size + uptime
```

## Features

- **3 bypass engines** — Linkvertise (3-strategy fallback chain), Work.ink, Lootlabs
- **Auto-detect** link type from URL
- **TTL cache** — results cached 10 min, instant re-requests
- **Rate limiting** — 30 req/min per IP
- **Browser fingerprinting** — rotates realistic User-Agents + headers
- **HTTP/2 support** via httpx
- **CORS enabled** — call it from any frontend

## Rate Limits

- 30 requests / minute per IP
- Cached results don't count against bypass engine limits
