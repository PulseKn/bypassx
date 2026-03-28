from fastapi import FastAPI, Query, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import time, os

from cache import cache
from bypasses.linkvertise import bypass_linkvertise
from bypasses.workink import bypass_workink
from bypasses.lootlabs import bypass_lootlabs

limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("BypassX Engine starting...")
    yield
    print("BypassX Engine shutting down.")

app = FastAPI(
    title="BypassX Engine",
    description="Custom ad-link bypass API — no third-party services",
    version="2.0.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def detect_type(url: str) -> str:
    url_lower = url.lower()
    if "linkvertise.com" in url_lower:
        return "linkvertise"
    if "work.ink" in url_lower or "delta" in url_lower:
        return "workink"
    if "loot-link.com" in url_lower or "lootlabs" in url_lower:
        return "lootlabs"
    return "unknown"


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "engine": "BypassX v2",
        "supported": ["linkvertise", "workink", "lootlabs"],
        "endpoints": {
            "bypass":  "GET /bypass?url=LINK&type=auto",
            "stats":   "GET /stats",
            "health":  "GET /health"
        }
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


@app.get("/stats", tags=["Info"])
async def stats():
    return {
        "cache_size": len(cache._store),
        "uptime_seconds": int(time.time() - cache._start_time),
    }


@app.get("/bypass", tags=["Bypass"])
@limiter.limit("30/minute")
async def bypass(
    request: Request,
    url: str = Query(..., description="Ad link URL to bypass"),
    type: str = Query("auto", description="auto | linkvertise | workink | lootlabs"),
):
    url = url.strip()

    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # Auto-detect
    link_type = detect_type(url) if type == "auto" else type

    if link_type == "unknown":
        raise HTTPException(status_code=400, detail="Unsupported link type. Supported: linkvertise, workink, lootlabs")

    # Check cache first
    cached = cache.get(url)
    if cached:
        return {
            "success": True,
            "cached": True,
            "type": link_type,
            "original": url,
            "result": cached,
            "timestamp": int(time.time())
        }

    # Run the right bypass engine
    try:
        if link_type == "linkvertise":
            result = await bypass_linkvertise(url)
        elif link_type == "workink":
            result = await bypass_workink(url)
        elif link_type == "lootlabs":
            result = await bypass_lootlabs(url)
        else:
            raise HTTPException(status_code=400, detail="Unknown type")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bypass engine error: {str(e)}")

    if not result:
        raise HTTPException(status_code=502, detail="Engine returned no result. Link may be expired or unsupported.")

    # Cache result for 10 minutes
    cache.set(url, result, ttl=600)

    return {
        "success": True,
        "cached": False,
        "type": link_type,
        "original": url,
        "result": result,
        "timestamp": int(time.time())
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"success": False, "detail": str(exc)})
