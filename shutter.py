#!/usr/bin/env python3
"""
SHUTTER — Your Learning Assistant
Watches your screen. Figures out what you're working on. Finds answers
before you ask. Runs 100% locally via Apple MLX.

Setup:
    python3 -m venv ~/shutter-env
    source ~/shutter-env/bin/activate
    pip install mlx mlx-vlm psutil pyobjc-framework-Quartz ddgs torch torchvision

    Then just:
    python3 shutter.py
"""

import os
os.environ["TRANSFORMERS_NO_FAST_IMAGE_PROCESSOR"] = "1"

import sys
import time
import subprocess
import tempfile
import re
import logging
from datetime import datetime

import psutil
from ddgs import DDGS
import Quartz

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

MODEL_ID = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
MIN_IDLE_SECONDS = 5           # brief pause before capture (avoid mid-keystroke)
MAX_IDLE_SECONDS = 600         # stop when user is clearly away
CHECK_INTERVAL_SECONDS = 15    # how often to poll
CYCLE_INTERVAL = 30            # 30 seconds for testing (increase for production)
FAILURE_COOLDOWN_SECONDS = 120 # 2 minutes after a quiet/failed cycle
MIN_RAM_AVAILABLE_GB = 1.0
MAX_RECENT_QUERIES = 3
LOG_FILE = os.path.expanduser("~/shutter.log")
SCREENSHOT_PATH = "/tmp/shutter_screen.png"
MAX_SESSION_LOG = 5            # how many recent screen descriptions to remember

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("shutter")

# ---------------------------------------------------------------------------
# MODEL — loads once, stays warm
# ---------------------------------------------------------------------------

_model = None
_processor = None
_recent_queries = []
_session_log = []


def load_model():
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


def run_text(prompt):
    """Run the model text-only (no image). Returns text."""
    load_model()
    from mlx_vlm import generate

    output = generate(
        _model, _processor, prompt, [],
        max_tokens=200, temperature=0.2, repetition_penalty=1.2, verbose=False,
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


# ---------------------------------------------------------------------------
# IDLE DETECTION
# ---------------------------------------------------------------------------

def get_idle_seconds():
    """How many seconds since the user last touched keyboard/mouse."""
    return Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateHIDSystemState,
        int(0xFFFFFFFF),
    )


# ---------------------------------------------------------------------------
# SYSTEM CHECK
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


# ---------------------------------------------------------------------------
# SCREENSHOT
# ---------------------------------------------------------------------------

def take_screenshot():
    """Silent screenshot, no shutter sound, saves to temp path."""
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
# SEARCH
# ---------------------------------------------------------------------------

def web_search(query):
    """Hit DuckDuckGo. No API key needed. Returns list of {title, url, snippet}."""
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=5))

        results = []
        for item in raw:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
            })
        return results

    except Exception as e:
        log.error(f"Search failed: {e}")
        return []


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
# DEDUPLICATION
# ---------------------------------------------------------------------------

def is_duplicate_query(query):
    """Check if this query is too similar to recent ones."""
    query_words = set(query.lower().split())
    for old_query in _recent_queries:
        old_words = set(old_query.lower().split())
        if not query_words or not old_words:
            continue
        overlap = len(query_words & old_words) / max(len(query_words), len(old_words))
        if overlap > 0.6:
            return True
    return False


def remember_query(query):
    """Track a successfully used query to prevent repeats."""
    _recent_queries.append(query)
    if len(_recent_queries) > MAX_RECENT_QUERIES:
        _recent_queries.pop(0)


# ---------------------------------------------------------------------------
# NOTIFY
# ---------------------------------------------------------------------------

def notify(title, message, url=None):
    """Send a macOS notification. Opens URL in default browser if provided."""
    import json as _json
    safe_title = _json.dumps(title[:100])
    safe_message = _json.dumps(message[:200])

    script = f'display notification {safe_message} with title {safe_title}'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log.warning(f"Notification script failed (exit {result.returncode}): {result.stderr.strip()}")
    except Exception as e:
        log.warning(f"Notification failed: {e}")

    if url:
        log.info(f"RESULT: {message} -> {url}")
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            log.warning(f"Failed to open URL {url}: {e}")
    else:
        log.info(f"RESULT: {message}")


# ---------------------------------------------------------------------------
# THE PIPELINE — screenshot -> analyze -> search -> notify
# ---------------------------------------------------------------------------

def run_pipeline():
    """Screenshot -> analyze -> search -> filter -> notify."""

    # 1. Screenshot
    log.info("Taking screenshot...")
    img = take_screenshot()
    if not img or not os.path.exists(img):
        log.error("No screenshot. Aborting.")
        return False

    # 2. Vision: describe what's on screen (with session memory)
    log.info("Analyzing screenshot...")
    session_ctx = get_session_context()
    vision_prompt = (
        "Describe what this person is doing in 2-3 sentences. "
        "What application are they using, what task are they doing, "
        "and what might they be stuck on? "
        "Be factual and concise."
    )
    if session_ctx:
        vision_prompt += f"\n\n{session_ctx}"

    screen_desc = run_vision(img, vision_prompt)

    log.info("=" * 50)
    log.info(f"I SEE: {screen_desc}")
    if _session_log:
        log.info(f"MEMORY: {len(_session_log)}/{MAX_SESSION_LOG} recent screens")
    log.info("=" * 50)

    remember_screen(screen_desc)

    # 3. Generate search query
    log.info("Generating search query...")
    query = run_text((
        "Generate a short web search query (under 10 words) to help "
        "this person with what they might be stuck on.\n\n"
        "Example input: Person is in Logic Pro, adjusting compressor on a vocal track\n"
        "Example output: logic pro vocal compressor settings\n\n"
        "Example input: Person is in Blender, working on UV unwrapping a mesh\n"
        "Example output: blender uv unwrap tutorial\n\n"
        "Example input: Person is in Final Cut Pro, adjusting color grading curves\n"
        "Example output: final cut pro color grading workflow\n\n"
        f"Input: {screen_desc[:300]}\n"
        "Output:"
    ))

    # Clean up query
    query = query.split('\n')[0].strip()
    query = ' '.join(query.split()[:12])
    query = sanitize_text(query)

    result = None

    if query and len(query) >= 10 and not is_duplicate_query(query):
        log.info(f"Search query: {query}")

        # 4. Search
        results = web_search(query)

        if results:
            # 5. Filter results
            log.info("Filtering results...")
            results_text = "\n\n".join(
                f"[{i+1}] {r['title']}\n{r['snippet']}\nURL: {r['url']}"
                for i, r in enumerate(results)
            )

            verdict = run_text((
                "You are a strict relevance filter. Given what someone is doing "
                "and these search results, decide: does any result answer their "
                "question or help with their task?\n\n"
                "Say NONE unless a result is clearly useful.\n\n"
                "If one result is genuinely helpful, respond with ONLY:\n"
                "NUMBER: [the result number]\n"
                "WHY: [one sentence]\n\n"
                "Otherwise respond with ONLY: NONE\n\n"
                f"What the person is doing:\n{screen_desc}\n\n"
                f"Search results:\n{results_text}"
            ))

            log.info(f"Filter verdict: {verdict}")

            if "NONE" not in verdict.upper():
                match = re.search(r'NUMBER:\s*(\d+)', verdict)
                why_match = re.search(r'WHY:\s*(.+)', verdict, re.IGNORECASE)

                if match:
                    idx = int(match.group(1)) - 1
                    if 0 <= idx < len(results):
                        result = results[idx]
                        result["why"] = why_match.group(1).strip() if why_match else results[idx]["title"]
                        remember_query(query)
    else:
        if query:
            log.info("Query too short, duplicate, or sanitized away. Skipping search.")

    # 6. Notify
    if result:
        notify("Shutter", result["why"], result["url"])

    # 7. Clean up screenshot
    try:
        os.remove(img)
    except OSError as e:
        log.warning(f"Failed to delete screenshot {img}: {e}")

    return result is not None


# ---------------------------------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("SHUTTER starting")
    log.info(f"Model: {MODEL_ID}")
    log.info(f"Cycle interval: {CYCLE_INTERVAL}s")
    log.info(f"Idle window: {MIN_IDLE_SECONDS}s-{MAX_IDLE_SECONDS}s")
    log.info("=" * 60)

    # pre-load the model so first analysis is fast
    log.info("Pre-loading model (this takes a minute on first run)...")
    load_model()
    log.info("Ready. Watching...")

    last_cycle = 0

    while True:
        try:
            time.sleep(CHECK_INTERVAL_SECONDS)

            # check if enough time since last cycle
            now = time.time()
            if now - last_cycle < CYCLE_INTERVAL:
                continue

            # check idle: need a brief pause but not too long
            idle = get_idle_seconds()
            if idle < MIN_IDLE_SECONDS:
                continue  # user is mid-keystroke
            if idle > MAX_IDLE_SECONDS:
                continue  # user is away

            log.info(f"Idle for {idle:.0f}s. Checking headroom...")

            # check system resources
            if not has_headroom():
                continue

            log.info("Running pipeline...")
            success = run_pipeline()

            if success:
                last_cycle = time.time()
                log.info("Cycle complete. Cooling down.")
            else:
                last_cycle = time.time() - CYCLE_INTERVAL + FAILURE_COOLDOWN_SECONDS
                log.info(f"Quiet cycle. Short cooldown ({FAILURE_COOLDOWN_SECONDS}s).")

        except KeyboardInterrupt:
            log.info("Shutting down.")
            break
        except Exception as e:
            log.error(f"Loop error: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
