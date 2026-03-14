"""
Shutter.app -- macOS menu bar application.

Wraps the Shutter platform (core.py, api.py, redact.py) in a native
menu bar app with its own Screen Recording permission entry.

Grant Screen Recording to Shutter.app only. Revoke it from Terminal.
Now every AI tool must go through Shutter's API to see your screen.
"""

import os
import sys
import threading
import subprocess
import logging
import time

import rumps

# When running as a py2app bundle, add the Resources directory to the
# Python path so core.py, api.py, etc. can be imported.
if getattr(sys, "frozen", False):
    resources_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0]))),
        "Resources",
    )
    if resources_dir not in sys.path:
        sys.path.insert(0, resources_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("shutter.app")


# ---------------------------------------------------------------------------
# PERMISSION CHECK
# ---------------------------------------------------------------------------

def has_screen_recording_permission():
    """Test if we have Screen Recording permission by taking a test screenshot."""
    import tempfile

    fd = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    path = fd.name
    fd.close()

    try:
        result = subprocess.run(
            ["screencapture", "-x", "-C", path],
            capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            return False
        # When permission is denied, screencapture produces a tiny or empty file
        return os.path.exists(path) and os.path.getsize(path) > 1000
    except Exception:
        return False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# MODEL DOWNLOAD PROGRESS
# ---------------------------------------------------------------------------

EXPECTED_MODEL_SIZE_GB = 5.0
HF_CACHE_DIR = os.path.expanduser(
    "~/.cache/huggingface/hub/models--mlx-community--Qwen3-VL-8B-Instruct-4bit"
)


def get_cache_size_gb():
    """Get the current size of the model cache directory in GB."""
    if not os.path.exists(HF_CACHE_DIR):
        return 0.0
    total = 0
    for dirpath, _, filenames in os.walk(HF_CACHE_DIR):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total / (1024 ** 3)


# ---------------------------------------------------------------------------
# THE APP
# ---------------------------------------------------------------------------

class ShutterApp(rumps.App):
    def __init__(self):
        super().__init__(
            "Shutter",
            icon="resources/menubar_icon.png",
            template=True,
            quit_button=None,
        )

        self._status_item = rumps.MenuItem("Status: Starting...")
        self._api_item = rumps.MenuItem("API: localhost:9494")
        self._api_item.set_callback(None)  # informational, not clickable
        self._permission_item = rumps.MenuItem(
            "Grant Screen Recording...",
            callback=self.open_permission_settings,
        )

        self.menu = [
            self._status_item,
            None,
            self._api_item,
            None,
            self._permission_item,
            rumps.MenuItem("About Shutter", callback=self.show_about),
            None,
            rumps.MenuItem("Quit Shutter", callback=self.quit_app),
        ]

        self.has_permission = False
        self.model_ready = False

    def did_launch(self):
        """Called after the run loop starts. Kick off startup in background."""
        threading.Thread(target=self._startup, daemon=True).start()

    def _set_status(self, text):
        """Update status menu item from any thread."""
        self._status_item.title = f"Status: {text}"

    # -- STARTUP --

    def _startup(self):
        """Background startup sequence."""
        # 1. Check Screen Recording permission
        log.info("Checking Screen Recording permission...")
        self.has_permission = has_screen_recording_permission()

        if not self.has_permission:
            self._set_status("No Screen Recording permission")
            rumps.notification(
                "Shutter",
                "Screen Recording Required",
                "Click the Shutter menu bar icon to grant permission.",
            )
            return

        log.info("Screen Recording permission confirmed.")
        self._permission_item.set_callback(None)  # grey out

        # 2. Start API server
        self._set_status("Starting API...")
        self._start_api()

        # 3. Load model (downloads ~5GB on first run)
        self._load_model_with_progress()

    def _start_api(self):
        """Start the FastAPI server in a daemon thread."""
        def run():
            import uvicorn
            from api import app
            uvicorn.run(app, host="127.0.0.1", port=9494, log_level="warning")

        threading.Thread(target=run, daemon=True).start()
        log.info("API server started on http://127.0.0.1:9494")

    def _load_model_with_progress(self):
        """Load the vision model, showing download progress in the menu."""
        import core

        # Start the actual model loading
        load_thread = threading.Thread(target=core.load_model, daemon=True)
        load_thread.start()

        # Poll cache directory for download progress
        while load_thread.is_alive():
            gb = get_cache_size_gb()
            if gb < EXPECTED_MODEL_SIZE_GB * 0.95:
                self._set_status(
                    f"Downloading model ({gb:.1f}GB / {EXPECTED_MODEL_SIZE_GB:.0f}GB)"
                )
            else:
                self._set_status("Loading model into memory...")
            time.sleep(2)

        self.model_ready = True
        self._set_status("Ready")
        log.info("Model loaded. Shutter is ready.")
        rumps.notification(
            "Shutter",
            "Ready",
            "Screen context API is running on localhost:9494",
        )

    # -- MENU CALLBACKS --

    def open_permission_settings(self, _):
        """Open System Settings to the Screen Recording pane."""
        subprocess.run([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
        ])
        rumps.alert(
            title="Grant Screen Recording",
            message=(
                "1. Find Shutter in the Screen Recording list\n"
                "   (or click '+' to add it)\n"
                "2. Toggle it ON\n"
                "3. Restart Shutter\n\n"
                "Shutter needs this permission to capture your screen.\n"
                "It's the only permission it needs."
            ),
            ok="Got it",
        )

    def show_about(self, _):
        """Show version and model info."""
        import core
        model_status = "loaded" if self.model_ready else "not loaded"
        rumps.alert(
            title="Shutter",
            message=(
                f"Version 0.1.0\n"
                f"Model: {core.MODEL_ID} ({model_status})\n"
                f"API: http://127.0.0.1:9494\n\n"
                f"Control what AI can see on your screen.\n"
                f"github.com/superlowburn/shutter"
            ),
            ok="OK",
        )

    def quit_app(self, _):
        log.info("Shutting down.")
        rumps.quit_application()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ShutterApp().run()
