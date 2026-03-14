# Spotter

Give any AI eyes on your Mac. Local, private, open source.

Spotter runs a vision model locally on your Mac and exposes an API so any AI
can ask "what's on this person's screen right now?" Everything stays on your
machine. Screenshots are captured, analyzed, and deleted. The only thing that
leaves is a sanitized text description -- and only when an AI asks for it.

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

Add to your Claude Code MCP config:

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
    "description": "User is in Logic Pro, adjusting a compressor on the vocal track.",
    "session_history": ["Previous screen description..."]
}
```

### `GET /screenshot`

Returns a PNG image of the current screen.

### `GET /health`

Returns server status and model info.

## How It Works

Spotter uses Qwen3-VL-8B (a vision-language model) running locally via Apple
MLX. When an AI requests screen context, Spotter:

1. Takes a silent screenshot (macOS screencapture)
2. Feeds it to the local vision model
3. Returns a sanitized text description of what's on screen
4. Deletes the screenshot

The model loads once and stays warm in memory (~5GB). First request takes
30-60 seconds (model loading). Subsequent requests take 5-10 seconds.

## Privacy

- Screenshots never leave your machine
- Only sanitized text descriptions are returned via the API
- Secrets, file paths, and tokens are automatically stripped
- The API only listens on localhost
- You opt in by starting the server

## Requirements

- macOS (Apple Silicon -- M1/M2/M3/M4)
- Python 3.11+
- ~5GB free RAM for the vision model
