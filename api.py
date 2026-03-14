"""
Shutter HTTP API — localhost:9494

GET /context     -> JSON screen description
GET /screenshot  -> PNG image
GET /health      -> server status

Bound to 127.0.0.1 only. Never expose this server beyond localhost.
"""

import base64
import logging
import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

import core

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("shutter.api")

app = FastAPI(
    title="Shutter",
    description="Local screen context API. Gives any AI eyes on your Mac.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# RATE LIMITING — simple in-process limiter, no extra dependencies
# ---------------------------------------------------------------------------

MAX_REQUESTS_PER_MINUTE = 10
_request_times: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(endpoint: str):
    """Raise 429 if endpoint has been called too many times in the last minute."""
    now = time.time()
    times = _request_times[endpoint]
    # Prune old entries
    _request_times[endpoint] = [t for t in times if t > now - 60]
    if len(_request_times[endpoint]) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limited. Max 10 requests/minute.")
    _request_times[endpoint].append(now)


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Check if the server is running."""
    return {"status": "ok", "model": core.MODEL_ID}


@app.get("/context")
def get_context():
    """
    Take a screenshot, analyze it with the local vision model,
    return structured text describing what's on screen.
    """
    _check_rate_limit("context")
    try:
        # Don't return session history in external API responses
        return core.get_screen_context(include_history=False)
    except RuntimeError as e:
        log.error(f"Context error: {e}")
        raise HTTPException(status_code=500, detail="Failed to capture screen context")


@app.get("/screenshot")
def get_screenshot():
    """Take a screenshot and return it as a PNG image."""
    _check_rate_limit("screenshot")
    try:
        result = core.get_screenshot_bytes()
        image_data = base64.b64decode(result["image_base64"])
        return Response(content=image_data, media_type="image/png")
    except RuntimeError as e:
        log.error(f"Screenshot error: {e}")
        raise HTTPException(status_code=500, detail="Failed to capture screenshot")


if __name__ == "__main__":
    import uvicorn
    log.info("Starting Shutter API on http://127.0.0.1:9494")
    log.info("WARNING: This server must never be exposed beyond localhost.")
    uvicorn.run(app, host="127.0.0.1", port=9494)
