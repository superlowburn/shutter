# Spotter Platform Design

## Problem

There's no standard way for AI to see what's on your screen. Every AI app that wants screen context builds its own pipeline -- screenshot capture, vision model, privacy controls -- from scratch. Users have no control over what gets shared or with whom.

## Solution

Spotter is a local API that gives any AI eyes on your Mac. It runs a vision model locally, takes screenshots on demand, and returns structured context ("user is in Logic Pro, adjusting a compressor on the vocal track") or raw images. Two protocols: HTTP for universal access, MCP for native integration with AI tools like Claude Code.

Everything runs locally. Screenshots never leave the machine. The user controls which apps have access.

## Target User

Developers and AI hackers who want screen awareness in their tools without building the vision pipeline themselves. The kind of person who adds MCP servers to Claude Code and builds local agents on weekends.

## What Ships

An open source GitHub repo. Three core files:

### core.py -- the engine

Extracted from the existing spotter.py. Contains:

- **Screenshot capture**: silent macOS screencapture
- **Model management**: loads Qwen3-VL-8B via Apple MLX, keeps it warm
- **Vision inference**: takes a screenshot path, runs the model, returns text
- **Session memory**: rolling log of last 5 screen descriptions for continuity
- **Sanitization**: strips secrets, paths, tokens from any text before it leaves
- **System checks**: RAM/CPU headroom verification before running inference

Two public functions that both servers call:

- `get_screen_context()` -> returns structured text describing what's on screen
- `get_screenshot()` -> returns the screenshot image (as bytes or path)

### api.py -- HTTP server

FastAPI on localhost:9494. Two endpoints:

- `GET /context` -> JSON with screen description, app name, task, session history
- `GET /screenshot` -> PNG image of the current screen

Localhost only. No auth needed -- if you can reach localhost, you're the user.

### mcp_server.py -- MCP server

FastMCP server with two tools:

- `see_screen` -> structured text (same as /context)
- `get_screenshot` -> the screenshot image

Users add it to their Claude Code MCP config. Claude can then see what they're working on.

## Architecture

```
[macOS Screen]
       |
       v
   core.py
   - take_screenshot()
   - load_model() (Qwen3-VL-8B via MLX, stays warm)
   - get_screen_context() -> structured text
   - get_screenshot() -> PNG image
   - session memory (last 5 screens)
   - sanitization (strip secrets)
       |
       +---> api.py (FastAPI, localhost:9494)
       |     GET /context -> JSON
       |     GET /screenshot -> PNG
       |
       +---> mcp_server.py (FastMCP)
             tool: see_screen -> text
             tool: get_screenshot -> image
```

No daemon. No polling loop. The model loads on first request and stays warm. Requests are on-demand.

## Privacy Model

1. Screenshots never leave the machine unless explicitly requested via get_screenshot
2. Default response is structured text, not raw images
3. All text output is sanitized (secrets, file paths, tokens stripped)
4. Localhost only -- no network exposure
5. The user explicitly opts in by starting the server or adding the MCP config
6. System headroom checks prevent performance impact

## What's NOT in v1

- App-level permissions (future: per-app access control like macOS accessibility)
- The learning assistant (search + notifications for creative software users -- separate product)
- Menu bar UI
- Auto-start on login
- Stuck detection
- Any form of remote access

## Relationship to Learning Assistant

The current spotter.py pipeline (screenshot -> vision -> search -> notify) gets split:

- **Screenshot + vision** moves into core.py (the platform)
- **Search + filter + notify** becomes a separate client script that calls the same API

The learning assistant is a consumer of the Spotter platform, not part of it. It ships separately as the paid App Store product for creative software users. The platform is the open source foundation.

## Tech Stack

- Python 3.11+
- Apple MLX (mlx-vlm) for local vision model inference
- Qwen3-VL-8B 4-bit (~5GB RAM)
- FastAPI + uvicorn for HTTP server
- FastMCP for MCP server
- macOS screencapture CLI (silent)
- psutil for system monitoring

## What Success Looks Like

- A developer can `pip install` and have the API running in under 2 minutes
- Claude Code users can add the MCP server and Claude immediately knows what app they're in
- The GitHub README demo takes 30 seconds to understand
- Someone forks it and builds something we didn't think of
