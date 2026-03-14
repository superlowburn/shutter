# SPOTTER

## What This Is

A macOS app that watches your screen, figures out what you're stuck on, searches for the answer, and surfaces it as a notification. Runs 100% locally using Apple MLX. Your screenshots never leave your machine. The only outbound call is a sanitized search query to DuckDuckGo.

**Target user:** Anyone learning creative software on Mac -- Logic Pro, Blender, Final Cut Pro, Photoshop, After Effects, Ableton. People who hit walls constantly and don't have the vocabulary to Google what they need.

**Core pitch:** "Spotter watches your screen and finds the answer before you ask."

---

## How It Works

Every 30 seconds (testing) / configurable interval (production):

1. Takes a silent screenshot
2. Analyzes it locally -- what app, what task, what you might be stuck on
3. Generates a short search query from the analysis
4. Searches DuckDuckGo
5. Filters results for the most relevant one
6. Sends a macOS notification with the answer and a link

**One model. One pipeline. One output. Everything stays on disk except a sanitized search query.**

---

## Architecture

```
[macOS Screen] --> screencapture (periodic)
       |
       v
[Qwen3-VL-8B via MLX (local)] --> "User is in Logic Pro, stuck on a compressor setting on the vocal track"
       |
       v
[Same model] --> Generate search query: "logic pro vocal compressor settings"
       |
       v
[DuckDuckGo] --> 5 results
       |
       v
[Same model] --> Filter: pick the best result (or none)
       |
       v
[macOS Notification] --> "Vocal compression in Logic Pro -- see: [link]"
```

---

## Trigger Model

**Testing phase (now):** Every 30 seconds. Minimal guards -- just headroom checks.

**Production:**
- Configurable interval (default 60-120 seconds)
- `MIN_IDLE_SECONDS = 5`: wait for a brief pause (avoid mid-keystroke captures)
- `MAX_IDLE_SECONDS = 600`: stop when user is clearly away
- So the capture window is: idle 5s-600s. Actively typing = wait. Gone for 10+ min = sleep.

**Future:** Real stuck detection -- repeated idle on same screen, app-switching between tool and browser, same view for too long. Not MVP.

---

## Tech Stack

- **Language:** Python 3.11+
- **ML Framework:** Apple MLX (mlx-vlm package)
- **Model:** Qwen3-VL-8B 4-bit (`mlx-community/Qwen3-VL-8B-Instruct-4bit`) -- ~5GB RAM, handles vision + text. Single model does screenshot analysis, query generation, and result filtering.
- **Repetition control:** `repetition_penalty=1.2` prevents output loops
- **Session memory:** Rolling log of last 5 screen descriptions, fed as context to each analysis for continuity
- **Screenshot:** macOS native `screencapture` CLI (silent, no shutter sound)
- **Idle Detection:** pyobjc (IOKit bindings for HID idle time)
- **System Monitoring:** psutil for CPU/memory pressure checks
- **Search:** DuckDuckGo via `ddgs` Python package (no API key, no account, no cost)
- **Notifications:** osascript for native macOS notifications
- **URL Delivery:** webbrowser module opens links in default browser

---

## Privacy

1. **NEVER send screenshots, file contents, or error logs over the network.** The only outbound data is the sanitized search query string.
2. **NEVER run inference when system headroom is low.** Check before running. Yield gracefully.
3. **NEVER keep screenshots longer than needed.** Capture, analyze, delete.
4. **Session memory stays local.** The rolling screen description log is never transmitted.
5. **Sanitize aggressively.** Strip anything that looks like a secret from search queries: long alphanumeric strings, file paths, tokens, passwords, API keys.
6. **The user should never notice this app is running.** If they feel a performance hit, back off.

---

## Market

**Who pays:** Mac users learning creative software. They hit walls constantly, can't articulate what they need in a search engine, and are already buying apps on the App Store with a card on file.

**Target apps:** Logic Pro, Blender, Final Cut Pro, Photoshop, After Effects, Ableton Live, DaVinci Resolve, Figma, Sketch.

**Why this works:** These users don't know the vocabulary. A guitarist learning Logic Pro doesn't know to search "sidechain compression routing." They just see a knob that isn't doing what they want. Spotter sees the screen and bridges the vocabulary gap.

**Distribution:** Mac App Store. Card on file, trust, discovery, no payment infrastructure to build.

**Pricing:** $4.99-9.99/mo subscription.

**Open source version:** A developer-focused version lives on GitHub. Builds the brand, attracts contributors, proves the tech. The App Store version is the revenue product -- polished, menu bar UI, auto-updates, no setup.

---

## What's Built

- Screenshot capture with silent mode
- Idle detection (min + max thresholds)
- System headroom checks (RAM + CPU)
- MLX model loading (lazy, stays warm)
- Vision analysis with chat template formatting
- Session memory (rolling 5-description log)
- Web search via DuckDuckGo
- Query sanitization (secrets, paths, tokens)
- Query deduplication (word overlap check)
- macOS notifications with URL opening
- Failure cooldown (short retry on quiet cycles)

## What's Next

1. **Fix query generation** -- the model echoes the full context instead of generating a short query. Prompt tuning problem: force short output, add examples, possibly constrain max_tokens.
2. **Validate the loop** -- run at 30s intervals, confirm screenshot-to-notification delivers something genuinely useful.
3. **Strip legacy code** -- remove social media / build-in-public features from spotter.py (see implementation notes below).
4. **Menu bar UI** -- rumps or rumps-alternative for status icon, pause/resume, settings.
5. **App Store packaging** -- py2app or pyinstaller, then Xcode wrapper for App Store submission.
6. **Stuck detection v2** -- smarter triggers based on user behavior patterns.

---

## Implementation Notes

What needs to change in `spotter.py` to match this spec:

### Config

| Setting | Current | Target |
|---------|---------|--------|
| `CYCLE_INTERVAL` | `600` (10 min) | `30` (testing) |

**Remove:** `POSTS_DIR`, `NUDGE_MODE`, `IDLE_NUDGE_THRESHOLD`, `PROJECT_DIRS`

### Functions to remove

- `find_active_git_dir()` -- git context no longer needed
- `get_git_context()` -- git context no longer needed
- `save_post()` -- no more social media post saving

### Pipeline simplification (`run_pipeline`)

Current pipeline has 8 steps. Simplified pipeline:

1. Screenshot
2. Vision: describe screen (update prompt -- "what app, what task, what might they be stuck on")
3. Generate search query (fix prompt -- force short output, add few-shot examples for creative software)
4. Search DuckDuckGo
5. Filter results (update prompt -- "does this help someone stuck in [app]?" not "better approach for building")
6. Notify (just: what Spotter sees + best link)
7. Clean up screenshot

**Remove:** interestingness gate (step 3 currently), git context (step 4), caption generation (step 5), nudge mode branching (step 6), post saving.

### Main loop

- Remove `POSTS_DIR` creation
- Simplify timing: run every `CYCLE_INTERVAL` seconds
- Keep idle guards and headroom checks

### Module docstring

Update from "build companion" to reflect the new product.
