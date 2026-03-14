"""
Spotter Core — the screen context engine.

Captures screenshots, runs a local vision model (Qwen3-VL-8B via Apple MLX),
maintains session memory, and sanitizes output. This module is the shared
foundation for both the HTTP API and MCP server.

Two public functions:
    get_screen_context()   -> structured text describing what's on screen
    get_screenshot_bytes() -> base64-encoded PNG of the screen
"""

import os
os.environ["TRANSFORMERS_NO_FAST_IMAGE_PROCESSOR"] = "1"

import base64
import subprocess
import tempfile
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
    """Return recent activity as context string for the model."""
    if not _session_log:
        return ""
    return "Recent activity:\n" + "\n".join(f"- {d[:100]}" for d in _session_log)


def get_session_history():
    """Return a copy of the raw session log."""
    return list(_session_log)


# ---------------------------------------------------------------------------
# SYSTEM CHECKS
# ---------------------------------------------------------------------------

def has_headroom():
    """Check if there's enough free RAM and CPU to run inference."""
    mem = psutil.virtual_memory()
    available_gb = mem.available / (1024 ** 3)
    cpu_pct = psutil.cpu_percent(interval=0.5)

    if available_gb < MIN_RAM_AVAILABLE_GB:
        log.info(f"Low RAM: {available_gb:.1f}GB available, need {MIN_RAM_AVAILABLE_GB}GB.")
        return False
    if cpu_pct > 80:
        log.info(f"CPU hot: {cpu_pct}%.")
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
    """Silent screenshot, no shutter sound. Returns temp file path or None."""
    path = tempfile.mktemp(suffix=".png", prefix="spotter_")
    try:
        subprocess.run(
            ["screencapture", "-x", "-C", path],
            check=True, capture_output=True,
        )
        return path
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

    Returns dict: {"description": "...", "session_history": [...]}
    Raises RuntimeError if screenshot fails or system has no headroom.
    """
    if not has_headroom():
        raise RuntimeError("System resources too low for inference")

    img = take_screenshot()
    if not img or not os.path.exists(img):
        raise RuntimeError("Screenshot capture failed")

    try:
        session_ctx = get_session_context()
        prompt = VISION_PROMPT
        if session_ctx:
            prompt += f"\n\n{session_ctx}"

        description = run_vision(img, prompt)
        description = sanitize_text(description)
        remember_screen(description)

        return {
            "description": description,
            "session_history": get_session_history(),
        }
    finally:
        try:
            os.remove(img)
        except OSError:
            pass


def get_screenshot_bytes():
    """
    Take a screenshot and return it as base64-encoded PNG.

    Returns dict: {"image_base64": "...", "content_type": "image/png"}
    Raises RuntimeError if screenshot fails.
    """
    img = take_screenshot()
    if not img or not os.path.exists(img):
        raise RuntimeError("Screenshot capture failed")

    try:
        with open(img, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        return {
            "image_base64": image_data,
            "content_type": "image/png",
        }
    finally:
        try:
            os.remove(img)
        except OSError:
            pass
