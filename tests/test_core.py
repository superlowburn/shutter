"""Tests for core module -- lightweight, no model loading needed."""
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
    from core import _session_log, remember_screen, MAX_SESSION_LOG
    _session_log.clear()
    for i in range(MAX_SESSION_LOG + 3):
        remember_screen(f"screen {i}")
    assert len(_session_log) == MAX_SESSION_LOG


def test_session_context_empty():
    from core import _session_log, get_session_context
    _session_log.clear()
    assert get_session_context() == ""


def test_session_context_has_content():
    from core import _session_log, remember_screen, get_session_context
    _session_log.clear()
    remember_screen("User is in Logic Pro editing a track")
    ctx = get_session_context()
    assert "Logic Pro" in ctx
    assert "Recent activity" in ctx


def test_session_history_returns_copy():
    from core import _session_log, remember_screen, get_session_history
    _session_log.clear()
    remember_screen("screen one")
    history = get_session_history()
    assert history == ["screen one"]
    # modifying the returned list shouldn't affect internal state
    history.append("fake")
    assert len(get_session_history()) == 1
