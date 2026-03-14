# Shutter

Control what AI can see on your screen. Local, private, open source.

Shutter is a permissions layer between your Mac's screen and AI. It runs a vision model locally on Apple Silicon, takes screenshots on demand, and returns sanitized text descriptions through a localhost API. AI tools get controlled glimpses of your screen -- not raw access.

Two protocols: HTTP for anything, MCP for Claude Code and other AI tools.

## Why

Every AI tool wants to see your screen. macOS Screen Recording permission is all-or-nothing. Shutter sits in the middle: grant Screen Recording only to Shutter, and every AI tool has to ask *it* for access. Shutter decides what to share, strips secrets and PII, and keeps a log of who asked.

## Quick Start

### Build the App

```bash
git clone https://github.com/superlowburn/shutter.git
cd shutter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python setup.py py2app -A
open dist/Shutter.app
```

Shutter appears in your menu bar. Click it and follow the prompt to grant Screen Recording permission. The vision model (~5GB) downloads automatically on first launch.

### The Privacy Move

Once Shutter.app is running:

1. Open System Settings > Privacy & Security > Screen Recording
2. Grant permission to **Shutter** (it should appear after first launch)
3. Revoke permission from **Terminal** (and any other apps)

Now Claude Code, Cursor, and every other AI tool must go through Shutter's API to see your screen. Shutter scrubs PII before they see anything.

### HTTP API

```bash
# What's on my screen?
curl http://localhost:9494/context

# Get a screenshot (PII already redacted)
curl http://localhost:9494/screenshot -o screen.png
```

### Claude Code (MCP)

Add to your Claude Code MCP config:

```json
{
    "mcpServers": {
        "shutter": {
            "command": "/path/to/venv/bin/python",
            "args": ["/path/to/shutter/mcp_server.py"]
        }
    }
}
```

Now Claude can see your screen. Try asking: "What am I working on right now?"

### Developer Mode

To run the API server directly (without the menu bar app):

```bash
python api.py
```

## API

### `GET /context`

Returns a JSON description of what's on screen:

```json
{
    "description": "User is in Logic Pro, adjusting a compressor on the vocal track.",
    "session_history": []
}
```

### `GET /screenshot`

Returns a PNG image of the current screen.

### `GET /health`

Returns server status and model info.

## How It Works

Shutter uses Qwen3-VL-8B (a vision-language model) running locally via Apple MLX. When an AI requests screen context, Shutter:

1. Takes a silent screenshot (macOS `screencapture`)
2. Runs OCR to detect and redact PII directly in the image (credit cards, SSNs, emails, phone numbers, IP addresses, crypto wallets, credentials)
3. Feeds the redacted image to the local vision model
4. Strips secrets and PII from the text output (defense in depth)
5. Returns a sanitized text description
6. Deletes the screenshot

The model loads once and stays warm in memory (~5GB). First request takes 30-60 seconds (model loading). Subsequent requests take 5-10 seconds.

## Privacy

- Screenshots never leave your machine
- PII is redacted from the screenshot image before the vision model or any consumer sees it
- Credit cards, SSNs, emails, phone numbers, IP addresses, crypto wallets, and credentials are detected via OCR and blacked out
- Text output is additionally scrubbed for secrets, file paths, and tokens (defense in depth)
- The API only listens on localhost (127.0.0.1)
- Rate limited to 10 requests/minute per endpoint
- Session history is not exposed through the external API
- You opt in by starting the server

## Requirements

- macOS (Apple Silicon -- M1/M2/M3/M4)
- Python 3.11+
- ~5GB free RAM for the vision model

## License

MIT
