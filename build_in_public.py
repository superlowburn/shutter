#!/usr/bin/env python3
"""
Build In Public -- watches your screen, generates shareable content.

Uses the Spotter platform to see what you're building, then crafts
tweet-length updates and blog-style notes. Everything stays local
until you choose to share.

    python build_in_public.py           # run continuously
    python build_in_public.py --dry-run # one cycle, print and exit
"""

import os
import sys
import time
import json
import logging
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

import core

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

CHECK_INTERVAL = 15          # seconds between idle checks
CYCLE_INTERVAL = 120         # seconds between content generation cycles
MIN_IDLE_SECONDS = 5         # wait for brief pause
MAX_IDLE_SECONDS = 600       # stop when user is away
FAILURE_COOLDOWN = 180       # 3 minutes after uninteresting cycle
MAX_RECENT_TOPICS = 5        # deduplication window

LOG_FILE = os.path.expanduser("~/build_in_public.log")
OUTPUT_FILE = os.path.expanduser("~/build_in_public.jsonl")

# Optional: drop content into personal_twitter queue
TWITTER_QUEUE_DIR = Path(os.path.expanduser(
    "~/claude/personal_twitter/content_queue"
))

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
log = logging.getLogger("bip")

# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------

_recent_topics = []


def is_duplicate_topic(topic):
    """Check if topic is too similar to recently generated content."""
    topic_words = set(topic.lower().split())
    for old in _recent_topics:
        old_words = set(old.lower().split())
        if not topic_words or not old_words:
            continue
        overlap = len(topic_words & old_words) / max(len(topic_words), len(old_words))
        if overlap > 0.6:
            return True
    return False


def remember_topic(topic):
    """Track generated topics for deduplication."""
    _recent_topics.append(topic)
    if len(_recent_topics) > MAX_RECENT_TOPICS:
        _recent_topics.pop(0)


# ---------------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------------

def notify(title, message):
    """macOS notification. Uses json.dumps for safe AppleScript escaping."""
    import json
    safe_title = json.dumps(title[:100])
    safe_message = json.dumps(message[:200])
    script = f'display notification {safe_message} with title {safe_title}'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        log.warning(f"Notification failed: {e}")


# ---------------------------------------------------------------------------
# CONTENT GENERATION PROMPTS
# ---------------------------------------------------------------------------

INTEREST_PROMPT = """You are filtering screen activity for a "build in public" feed.

The person is an indie hacker building software and making music.

Given this screen description, decide: is this something worth sharing publicly?

SHARE if they are: writing code, designing UI, producing music, configuring
dev tools, debugging, deploying, working in a DAW, working in a creative app,
writing documentation, or doing anything that shows the build process.

SKIP if they are: reading email, browsing social media, watching videos,
in a chat app, doing nothing interesting, or doing something private.

Respond with ONLY one line:
SHARE: [one-sentence reason why this is shareable]
or
SKIP

Screen description: {description}

Recent activity:
{history}"""

TWEET_PROMPT = """Write a single tweet (max 280 characters) about what this indie hacker is doing right now.

Rules:
- First person ("I" not "they")
- No hashtags
- No exclamation marks
- Sound like a builder posting notes, not a marketer
- Be specific about the tool or task, not vague
- Max 1-2 sentences

What they're doing: {description}
Context: {reason}

Tweet:"""

BLOG_PROMPT = """Write a short build log entry (2-4 sentences) about what this indie hacker is working on.

Rules:
- First person
- Casual but specific
- Mention the tool/app by name
- Include what the challenge or goal is
- No hype words

What they're doing: {description}
Context: {reason}

Entry:"""


# ---------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------

def run_pipeline():
    """Screen context -> interest filter -> content generation -> save."""

    # 1. Get screen context from the platform
    log.info("Getting screen context...")
    try:
        ctx = core.get_screen_context()
    except RuntimeError as e:
        log.warning(f"Screen context failed: {e}")
        return None

    description = ctx["description"]
    history = ctx.get("session_history", [])
    history_str = "\n".join(f"- {h[:100]}" for h in history) if history else "(none)"

    log.info(f"Screen: {description[:100]}")

    # 2. Interest filter
    log.info("Checking if this is shareable...")
    verdict = core.run_text(INTEREST_PROMPT.format(
        description=description,
        history=history_str,
    ))
    log.info(f"Verdict: {verdict}")

    if verdict.strip().upper().startswith("SKIP"):
        log.info("Not interesting enough to share. Skipping.")
        return None

    # Extract reason from "SHARE: reason"
    reason = verdict
    if ":" in verdict:
        reason = verdict.split(":", 1)[1].strip()

    # 3. Deduplication
    if is_duplicate_topic(description):
        log.info("Too similar to recent content. Skipping.")
        return None

    # 4. Generate tweet
    log.info("Generating tweet...")
    tweet = core.run_text(TWEET_PROMPT.format(
        description=description,
        reason=reason,
    ))
    tweet = tweet.split("\n")[0].strip().strip('"').strip("'")
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."

    # 5. Generate blog entry
    log.info("Generating blog entry...")
    blog = core.run_text(BLOG_PROMPT.format(
        description=description,
        reason=reason,
    ))
    blog = blog.strip().strip('"')

    # 6. Build output record
    record = {
        "timestamp": datetime.now().isoformat(),
        "screen_description": description,
        "reason": reason,
        "tweet": tweet,
        "blog": blog,
        "status": "draft",
    }

    # 7. Save to JSONL log (owner-only permissions)
    log.info(f"Tweet: {tweet}")
    log.info(f"Blog: {blog[:100]}...")
    fd = os.open(OUTPUT_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(record) + "\n")
    log.info(f"Saved to {OUTPUT_FILE}")

    # 8. Optionally drop into Twitter content queue
    if TWITTER_QUEUE_DIR.exists():
        save_to_twitter_queue(record)

    # 9. Notify
    notify("Build in Public", tweet)

    # 10. Remember topic for dedup
    remember_topic(description)

    return record


def save_to_twitter_queue(record):
    """Save content to personal_twitter content_queue for dashboard visibility."""
    now = datetime.now()
    filename = f"bip_{now.strftime('%Y-%m-%d_%H%M%S')}.json"
    path = TWITTER_QUEUE_DIR / filename

    queue_entry = {
        "type": "build_in_public",
        "track": "build_in_public",
        "created_at": record["timestamp"],
        "status": "draft",
        "content": record["tweet"],
        "blog_entry": record["blog"],
        "screen_context": record["screen_description"],
        "priority": "NORMAL",
        "tags": ["bip", "auto-generated"],
    }

    with open(path, "w") as f:
        json.dump(queue_entry, f, indent=2)
    log.info(f"Saved to Twitter queue: {path}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build In Public -- screen watcher")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run one cycle, print output, and exit")
    args = parser.parse_args()

    if args.dry_run:
        log.info("Dry run: one cycle...")
        core.load_model()
        result = run_pipeline()
        if result:
            print("\n--- TWEET ---")
            print(result["tweet"])
            print("\n--- BLOG ---")
            print(result["blog"])
        else:
            print("\nNo content generated (screen wasn't interesting or screenshot failed).")
        return

    log.info("=" * 60)
    log.info("BUILD IN PUBLIC starting")
    log.info(f"Cycle interval: {CYCLE_INTERVAL}s")
    log.info(f"Output: {OUTPUT_FILE}")
    log.info("=" * 60)

    core.load_model()
    log.info("Ready. Watching...")

    last_cycle = 0

    while True:
        try:
            time.sleep(CHECK_INTERVAL)

            now = time.time()
            if now - last_cycle < CYCLE_INTERVAL:
                continue

            idle = core.get_idle_seconds()
            if idle < MIN_IDLE_SECONDS:
                continue
            if idle > MAX_IDLE_SECONDS:
                continue

            if not core.has_headroom():
                continue

            log.info(f"Idle {idle:.0f}s. Running pipeline...")
            result = run_pipeline()

            if result:
                last_cycle = time.time()
                log.info("Content generated. Cooling down.")
            else:
                last_cycle = time.time() - CYCLE_INTERVAL + FAILURE_COOLDOWN
                log.info("No content this cycle. Short cooldown.")

        except KeyboardInterrupt:
            log.info("Shutting down.")
            break
        except Exception as e:
            log.error(f"Loop error: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
