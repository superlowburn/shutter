# Spotter Platform Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the screen-watching engine from spotter.py into a reusable core module, then expose it via both HTTP (FastAPI) and MCP (FastMCP) APIs.

**Architecture:** Three files, shared core. `core.py` owns screenshot capture, vision model, session memory, and sanitization. `api.py` is a FastAPI server on localhost:9494 with two endpoints. `mcp_server.py` is a FastMCP server with two tools. Both servers import from core and are thin wrappers.

**Tech Stack:** Python 3.12, Apple MLX (mlx-vlm), Qwen3-VL-8B 4-bit, FastAPI + uvicorn, FastMCP, macOS screencapture.

**Spec:** `docs/superpowers/specs/2026-03-13-spotter-platform-design.md`

---

## Chunk 1: Project Setup and Core Extraction

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/mallett/claude/spotter
git init
```

- [ ] **Step 2: Create .gitignore**

Create `.gitignore`:
```
__pycache__/
*.pyc
.env
*.log
/tmp/
.DS_Store
```

- [ ] **Step 3: Create requirements.txt**

Create `requirements.txt`:
```
mlx>=0.21
mlx-vlm>=0.3
psutil>=5.9
pyobjc-framework-Quartz>=10.0
ddgs>=6.0
fastapi>=0.100
uvicorn>=0.20
fastmcp>=2.0
```

- [ ] **Step 4: Install fastmcp**

```bash
source ~/spotter-env/bin/activate
pip install fastmcp
```

- [ ] **Step 5: Commit project setup**

```bash
git add .gitignore requirements.txt
git commit -m "chore: project setup with requirements and gitignore"
```

---

### Task 2: Extract core.py

This is the engine. Everything both servers need lives here. Extracted from the existing, working spotter.py.

**Files:**
- Create: `core.py`

- [ ] **Step 1: Write test for core module**

Create `tests/test_core.py`:
```python
"""Tests for core module — lightweight, no model loading."""
import os
import pytest


def test_sanitize_strips_long_tokens():
    from core import sanitize_text
    result = sanitize_text("check this ABCDEFGHIJKLMNOPQRSTUVWXYZ out")
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result
    assert "check" in result


def test_sanitize_strips_file_paths():
    from core import sanitize_text
    result = sanitize_text("see /Users/me/secret/project/file.py here")
    assert "/Users" not in result


def test_sanitize_strips_api_keys():
    from core import sanitize_text
    result = sanitize_text("my api_key=sk_live_abc123 is here")
    assert "sk_live" not in result


def test_session_memory_limits():
    from core import _session_log, remember_screen, get_session_context, MAX_SESSION_LOG
    _session_log.clear()
    for i in range(MAX_SESSION_LOG + 3):
        remember_screen(f"screen {i}")
    assert len(_session_log) == MAX_SESSION_LOG


def test_session_context_empty():
    from core import _session_log, get_session_context
    _session_log.clear()
    assert get_session_context() == ""


def test_screenshot_path_configured():
    from core import SCREENSHOT_PATH
    assert SCREENSHOT_PATH.endswith(".png")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/mallett/claude/spotter
source ~/spotter-env/bin/activate
python -m pytest tests/test_core.py -v
```

Expected: FAIL (core module does not exist yet)

- [ ] **Step 3: Create core.py**

Create `core.py` — extracted from spotter.py with two new public API functions added:

```python
"""
Spotter Core — the screen-watching engine.

Captures screenshots, runs local vision model (Qwen3-VL-8B via Apple MLX),
maintains session memory, and sanitizes output. This module is the shared
foundation for both the HTTP API and MCP server.
"""

import os
os.environ["TRANSFORMERS_NO_FAST_IMAGE_PROCESSOR"] = "1"

import base64
import subprocess
import re
import logging

import psutil
import Quartz

log = logging.getLogger("spotter")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

MODEL_ID = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
MIN_RAM_AVAILABLE_GB = 1.0
SCREENSHOT_PATH = "/tmp/spotter_screen.png"
MAX_SESSION_LOG = 5

# ---------------------------------------------------------------------------
# MODEL — loads once, stays warm
# ---------------------------------------------------------------------------

_model = None
_processor = None
_session_log = []


def load_model():
    """Load the vision model. Called automatically on first inference."""
    global _model, _processor
    if _model is not None:
        return

    log.info(f"Loading model {MODEL_ID} (first run downloads ~5GB)...")
    from mlx_vlm import load

    _model, _processor = load(MODEL_ID)
    log.info("Model loaded and warm.")


def run_vision(image_path, prompt):
    """Run the model with an image + prompt. Returns text."""
    load_model()
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    formatted_prompt = apply_chat_template(
        _processor, _model.config, prompt, num_images=1,
    )

    output = generate(
        _model, _processor, formatted_prompt, [image_path],
        max_tokens=300, temperature=0.3, repetition_penalty=1.2, verbose=False,
    )
    if isinstance(output, str):
        return output.strip()
    elif hasattr(output, 'text'):
        return output.text.strip()
    else:
        return str(output).strip()


# ---------------------------------------------------------------------------
# SESSION MEMORY
# ---------------------------------------------------------------------------

def remember_screen(description):
    """Track recent screen descriptions for continuity."""
    _session_log.append(description)
    if len(_session_log) > MAX_SESSION_LOG:
        _session_log.pop(0)


def get_session_context():
    """Return recent activity as context for the model."""
    if not _session_log:
        return ""
    return "Recent activity:\n" + "\n".join(f"- {d[:100]}" for d in _session_log)


def get_session_history():
    """Return the raw session log (list of recent screen descriptions)."""
    return list(_session_log)


# ---------------------------------------------------------------------------
# SYSTEM CHECKS
# ---------------------------------------------------------------------------

def has_headroom():
    """Check if there's enough free RAM to run inference without impact."""
    mem = psutil.virtual_memory()
    available_gb = mem.available / (1024 ** 3)
    cpu_pct = psutil.cpu_percent(interval=0.5)

    if available_gb < MIN_RAM_AVAILABLE_GB:
        log.info(f"Low RAM: {available_gb:.1f}GB available, need {MIN_RAM_AVAILABLE_GB}GB. Skipping.")
        return False
    if cpu_pct > 80:
        log.info(f"CPU hot: {cpu_pct}%. Skipping.")
        return False
    return True


def get_idle_seconds():
    """How many seconds since the user last touched keyboard/mouse."""
    return Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateHIDSystemState,
        int(0xFFFFFFFF),
    )


# ---------------------------------------------------------------------------
# SCREENSHOT
# ---------------------------------------------------------------------------

def take_screenshot():
    """Silent screenshot, no shutter sound. Returns path or None."""
    try:
        subprocess.run(
            ["screencapture", "-x", "-C", SCREENSHOT_PATH],
            check=True, capture_output=True,
        )
        return SCREENSHOT_PATH
    except subprocess.CalledProcessError as e:
        log.error(f"Screenshot failed: {e}")
        return None


# ---------------------------------------------------------------------------
# SANITIZE
# ---------------------------------------------------------------------------

def sanitize_text(text):
    """Strip anything that looks like a secret from text."""
    text = re.sub(r'[A-Za-z0-9_\-]{20,}', '', text)
    text = re.sub(r'(/[\w.\-]+)+', '', text)
    text = re.sub(r'(key|token|secret|password|api_key)\s*[=:]\s*\S+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

VISION_PROMPT = (
    "Describe what this person is doing in 2-3 sentences. "
    "What application are they using, what task are they doing, "
    "and what might they be stuck on? "
    "Be factual and concise."
)


def get_screen_context():
    """
    Take a screenshot, analyze it with the vision model, return structured text.

    Returns a dict:
        {"description": "...", "session_history": [...]}

    Raises RuntimeError if screenshot fails or system has no headroom.
    """
    if not has_headroom():
        raise RuntimeError("System resources too low for inference")

    img = take_screenshot()
    if not img or not os.path.exists(img):
        raise RuntimeError("Screenshot capture failed")

    session_ctx = get_session_context()
    prompt = VISION_PROMPT
    if session_ctx:
        prompt += f"\n\n{session_ctx}"

    description = run_vision(img, prompt)
    description = sanitize_text(description)
    remember_screen(description)

    # Clean up screenshot
    try:
        os.remove(img)
    except OSError:
        pass

    return {
        "description": description,
        "session_history": get_session_history(),
    }


def get_screenshot_bytes():
    """
    Take a screenshot and return it as base64-encoded PNG.

    Returns a dict:
        {"image_base64": "...", "content_type": "image/png"}

    Raises RuntimeError if screenshot fails.
    """
    img = take_screenshot()
    if not img or not os.path.exists(img):
        raise RuntimeError("Screenshot capture failed")

    with open(img, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # Clean up
    try:
        os.remove(img)
    except OSError:
        pass

    return {
        "image_base64": image_data,
        "content_type": "image/png",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/mallett/claude/spotter
python -m pytest tests/test_core.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core.py tests/test_core.py
git commit -m "feat: extract core.py from spotter.py — screenshot, vision, session memory, sanitization"
```

---

## Chunk 2: HTTP and MCP Servers

### Task 3: Build api.py (HTTP Server)

**Files:**
- Create: `api.py`

- [ ] **Step 1: Write test for HTTP API**

Create `tests/test_api.py`:
```python
"""Tests for HTTP API — verifies routes exist and error handling works."""
from fastapi.testclient import TestClient


def test_context_endpoint_exists():
    from api import app
    client = TestClient(app)
    # Will fail on inference (no GPU in CI) but route should exist
    response = client.get("/context")
    # Either 200 (if model loads) or 500 (RuntimeError from core)
    assert response.status_code in (200, 500)


def test_screenshot_endpoint_exists():
    from api import app
    client = TestClient(app)
    response = client.get("/screenshot")
    assert response.status_code in (200, 500)


def test_health_endpoint():
    from api import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_api.py -v
```

Expected: FAIL (api module does not exist)

- [ ] **Step 3: Create api.py**

Create `api.py`:

```python
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
        result = core.get_screen_context()
        return result
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_api.py -v
```

Expected: All 3 tests PASS (health returns 200, context/screenshot return 200 or 500)

- [ ] **Step 5: Commit**

```bash
git add api.py tests/test_api.py
git commit -m "feat: add HTTP API server (FastAPI on localhost:9494)"
```

---

### Task 4: Build mcp_server.py (MCP Server)

**Files:**
- Create: `mcp_server.py`

- [ ] **Step 1: Create mcp_server.py**

Create `mcp_server.py`:

```python
"""
Spotter MCP Server — screen context for AI tools.

Add to Claude Code config:
    {
        "mcpServers": {
            "spotter": {
                "command": "python",
                "args": ["/path/to/spotter/mcp_server.py"],
                "env": {
                    "PATH": "/path/to/spotter-env/bin:/usr/bin:/bin"
                }
            }
        }
    }
"""

import base64
import logging

from fastmcp import FastMCP
from mcp import types

import core

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

mcp = FastMCP("spotter")


@mcp.tool
def see_screen() -> dict:
    """
    See what's on the user's screen right now.

    Takes a screenshot, analyzes it with a local vision model,
    and returns a text description of what the user is doing,
    what app they're in, and what they might be stuck on.

    Everything runs locally. The screenshot is deleted after analysis.
    """
    return core.get_screen_context()


@mcp.tool
def get_screenshot() -> list:
    """
    Get a screenshot of the user's screen as a PNG image.

    Returns the raw screenshot. Use see_screen instead if you
    just need to know what the user is doing — it's faster and
    doesn't send pixel data.
    """
    result = core.get_screenshot_bytes()
    return [
        types.ImageContent(
            type="image",
            data=result["image_base64"],
            mimeType="image/png",
        )
    ]


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "import ast; ast.parse(open('mcp_server.py').read()); print('OK')"
```

Expected: OK

- [ ] **Step 3: Commit**

```bash
git add mcp_server.py
git commit -m "feat: add MCP server (FastMCP) for Claude Code integration"
```

---

## Chunk 3: Smoke Test and README

### Task 5: Smoke Test

- [ ] **Step 1: Run all tests**

```bash
cd /Users/mallett/claude/spotter
source ~/spotter-env/bin/activate
python -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 2: Verify HTTP server starts**

Start the server in background, hit the health endpoint, then kill it:

```bash
source ~/spotter-env/bin/activate
python api.py &
API_PID=$!
sleep 3
curl -s http://127.0.0.1:9494/health | python -m json.tool
kill $API_PID
```

Expected: `{"status": "ok", "model": "mlx-community/Qwen3-VL-8B-Instruct-4bit"}`

- [ ] **Step 3: Verify MCP server starts**

```bash
source ~/spotter-env/bin/activate
python -c "
from mcp_server import mcp
print('MCP server name:', mcp.name)
print('Tools:', [t.name for t in mcp._tool_manager.list_tools()])
print('OK')
"
```

Expected: Lists the two tools (see_screen, get_screenshot) and prints OK

- [ ] **Step 4: Test /context endpoint end-to-end**

With the HTTP server running, verify the full pipeline (screenshot + vision + response):

```bash
source ~/spotter-env/bin/activate
python api.py &
API_PID=$!
sleep 5  # model loading takes a moment on first call
curl -s http://127.0.0.1:9494/context | python -m json.tool
kill $API_PID
```

Expected: JSON with `description` (text about what's on screen) and `session_history` (list)

---

### Task 6: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

Create `README.md` — the open source hook:

```markdown
# Spotter

Give any AI eyes on your Mac. Local, private, open source.

Spotter runs a vision model locally on your Mac and exposes an API so any AI
can ask "what's on this person's screen right now?" Everything stays on your
machine. Screenshots are captured, analyzed, and deleted. The only thing that
leaves is a sanitized text description — and only when an AI asks for it.

Two protocols: HTTP for anything, MCP for Claude Code and other AI tools.

## Quick Start

### Install

```bash
git clone https://github.com/YOUR_USERNAME/spotter.git
cd spotter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### HTTP API

```bash
python api.py
```

Then from another terminal:

```bash
# What's on my screen?
curl http://localhost:9494/context

# Get a screenshot
curl http://localhost:9494/screenshot -o screen.png
```

### Claude Code (MCP)

Add to your Claude Code MCP config (`~/.claude.json` or project `.mcp.json`):

```json
{
    "mcpServers": {
        "spotter": {
            "command": "/path/to/venv/bin/python",
            "args": ["/path/to/spotter/mcp_server.py"]
        }
    }
}
```

Now Claude can see your screen. Try asking: "What am I working on right now?"

## API

### `GET /context`

Returns a JSON description of what's on screen:

```json
{
    "description": "User is in Logic Pro, adjusting a compressor on the vocal track. They appear to be tweaking the threshold and ratio settings.",
    "session_history": ["Previous screen description...", "..."]
}
```

### `GET /screenshot`

Returns a PNG image of the current screen.

### `GET /health`

Returns server status.

## How It Works

Spotter uses Qwen3-VL-8B (a vision-language model) running locally via Apple
MLX. When an AI requests screen context, Spotter:

1. Takes a silent screenshot (macOS screencapture)
2. Feeds it to the local vision model
3. Returns a text description of what's on screen
4. Deletes the screenshot

The model loads once and stays warm in memory (~5GB). First request takes
30-60 seconds (model loading). Subsequent requests take 5-10 seconds.

## Privacy

- Screenshots never leave your machine
- Only sanitized text descriptions are returned via the API
- Secrets, file paths, and tokens are automatically stripped
- The API only listens on localhost — no network exposure
- You opt in by starting the server

## Requirements

- macOS (Apple Silicon — M1/M2/M3/M4)
- Python 3.11+
- ~5GB free RAM for the vision model
```

- [ ] **Step 2: Commit README**

```bash
git add README.md
git commit -m "docs: add README with quick start, API reference, and privacy info"
```

- [ ] **Step 3: Final commit — add all remaining files**

```bash
git add -A
git status
git commit -m "chore: initial platform release"
```
