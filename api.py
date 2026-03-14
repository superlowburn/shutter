"""
Spotter HTTP API — localhost:9494

GET /context     -> JSON screen description
GET /screenshot  -> PNG image
GET /health      -> server status
"""

import base64
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

import core

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(
    title="Spotter",
    description="Local screen context API. Gives any AI eyes on your Mac.",
    version="0.1.0",
)


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
    try:
        return core.get_screen_context()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/screenshot")
def get_screenshot():
    """Take a screenshot and return it as a PNG image."""
    try:
        result = core.get_screenshot_bytes()
        image_data = base64.b64decode(result["image_base64"])
        return Response(content=image_data, media_type="image/png")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9494)
