"""Tests for core module -- lightweight, no model loading needed."""
import time


# ---------------------------------------------------------------------------
# SANITIZATION — original tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# SANITIZATION — new patterns (security audit H1)
# ---------------------------------------------------------------------------

def test_sanitize_strips_credit_cards():
    from core import sanitize_text
    result = sanitize_text("card 4111 1111 1111 1111 on file")
    assert "4111" not in result
    assert "[REDACTED]" in result


def test_sanitize_strips_credit_cards_no_spaces():
    from core import sanitize_text
    result = sanitize_text("card 4111111111111111 on file")
    assert "4111" not in result


def test_sanitize_strips_ssn():
    from core import sanitize_text
    result = sanitize_text("SSN is 123-45-6789 here")
    assert "123-45-6789" not in result
    assert "[REDACTED]" in result


def test_sanitize_strips_email():
    from core import sanitize_text
    result = sanitize_text("email alice@example.com visible")
    assert "alice@example.com" not in result
    assert "[REDACTED]" in result


def test_sanitize_strips_uuid():
    from core import sanitize_text
    result = sanitize_text("id 550e8400-e29b-41d4-a716-446655440000 here")
    assert "550e8400" not in result
    assert "[REDACTED]" in result


def test_sanitize_strips_windows_paths():
    from core import sanitize_text
    result = sanitize_text("file at C:\\Users\\Alice\\secrets.txt")
    assert "Alice" not in result
    assert "[PATH]" in result


def test_sanitize_strips_bearer_token():
    from core import sanitize_text
    result = sanitize_text("bearer: eyJhbGciOiJIUz stuff")
    assert "eyJhbGci" not in result


def test_sanitize_strips_shorter_tokens():
    from core import sanitize_text
    # 15-char token should be caught
    result = sanitize_text("token abc123def456ghi visible")
    assert "abc123def456ghi" not in result


# ---------------------------------------------------------------------------
# SESSION MEMORY
# ---------------------------------------------------------------------------

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


def test_session_ttl_expiry():
    from core import _session_log, SESSION_TTL, get_session_history
    _session_log.clear()
    # Add an entry with a timestamp in the past
    _session_log.append((time.time() - SESSION_TTL - 10, "old entry"))
    _session_log.append((time.time(), "new entry"))
    history = get_session_history()
    assert len(history) == 1
    assert history[0] == "new entry"
