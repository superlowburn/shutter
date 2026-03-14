"""Tests for build_in_public.py — deduplication, truncation, output format."""

import json
import tempfile
import os
from pathlib import Path

import build_in_public as bip


# ---------------------------------------------------------------------------
# DEDUPLICATION
# ---------------------------------------------------------------------------

def test_duplicate_exact_match():
    """Identical topics should be caught as duplicates."""
    bip._recent_topics.clear()
    bip.remember_topic("working in Logic Pro on vocal compression")
    assert bip.is_duplicate_topic("working in Logic Pro on vocal compression") is True


def test_duplicate_high_overlap():
    """Topics with >60% word overlap should be caught."""
    bip._recent_topics.clear()
    bip.remember_topic("working in Logic Pro on vocal compression settings")
    # shares 5/7 words = 71%
    assert bip.is_duplicate_topic("working in Logic Pro on vocal EQ settings") is True


def test_not_duplicate_different_topic():
    """Unrelated topics should not be flagged."""
    bip._recent_topics.clear()
    bip.remember_topic("working in Logic Pro on vocal compression")
    assert bip.is_duplicate_topic("debugging Python API server in VS Code") is False


def test_not_duplicate_empty_history():
    """With no history, nothing is a duplicate."""
    bip._recent_topics.clear()
    assert bip.is_duplicate_topic("anything at all") is False


# ---------------------------------------------------------------------------
# TOPIC MEMORY
# ---------------------------------------------------------------------------

def test_remember_topic_window_size():
    """Topic memory should not exceed MAX_RECENT_TOPICS."""
    bip._recent_topics.clear()
    for i in range(10):
        bip.remember_topic(f"topic number {i}")
    assert len(bip._recent_topics) == bip.MAX_RECENT_TOPICS


def test_remember_topic_fifo():
    """Oldest topic should be evicted first."""
    bip._recent_topics.clear()
    for i in range(bip.MAX_RECENT_TOPICS + 2):
        bip.remember_topic(f"topic {i}")
    assert "topic 0" not in bip._recent_topics[0]
    assert "topic 1" not in bip._recent_topics[0]


# ---------------------------------------------------------------------------
# TWITTER QUEUE FORMAT
# ---------------------------------------------------------------------------

def test_save_to_twitter_queue_format():
    """Queue entries should have the expected fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = bip.TWITTER_QUEUE_DIR
        bip.TWITTER_QUEUE_DIR = Path(tmpdir)

        record = {
            "timestamp": "2026-03-13T23:45:00",
            "screen_description": "User is in VS Code editing Python",
            "reason": "Writing code",
            "tweet": "Working on the API server today.",
            "blog": "Spent the afternoon on the API layer.",
            "status": "draft",
        }
        bip.save_to_twitter_queue(record)

        files = list(Path(tmpdir).glob("bip_*.json"))
        assert len(files) == 1

        with open(files[0]) as f:
            entry = json.load(f)

        assert entry["type"] == "build_in_public"
        assert entry["status"] == "draft"
        assert entry["content"] == record["tweet"]
        assert entry["blog_entry"] == record["blog"]
        assert "bip" in entry["tags"]

        bip.TWITTER_QUEUE_DIR = original_dir
