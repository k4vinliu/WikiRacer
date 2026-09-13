"""speedrun/race.py — the MediaWiki title lookup and the two page sources. Offline."""

from __future__ import annotations

import io
import ssl
import urllib.error
from urllib.parse import parse_qs, urlparse

import pytest

from speedrun import race, steel_client
from speedrun.types import SessionHandle

# VERBATIM from a live action=query call on 2026-09-12 (docs/steel-json-shapes.md).
QUERY = {"batchcomplete": True, "query": {
    "normalized": [{"fromencoded": False, "from": "barack obama", "to": "Barack obama"},
                   {"fromencoded": False, "from": "a#b", "to": "A"}],
    "redirects": [{"from": "WWII", "to": "World War II"}, {"from": "Café", "to": "Coffeehouse"},
                  {"from": "Snakes", "to": "Snake"}, {"from": "Barack obama", "to": "Barack Obama"}],
    "pages": [{"ns": 0, "title": "NotARealArticleXyzzy", "missing": True},
              {"pageid": 290, "ns": 0, "title": "A"},
              {"pageid": 23862, "ns": 0, "title": "Python (programming language)"},
              {"pageid": 29370, "ns": 0, "title": "Snake"},
              {"pageid": 32927, "ns": 0, "title": "World War II"},
              {"pageid": 370815, "ns": 0, "title": "Coffeehouse"},
              {"pageid": 534366, "ns": 0, "title": "Barack Obama"},
              {"pageid": 17673008, "ns": 1, "title": "Talk:Cat"},
              {"pageid": 23372115, "ns": 0, "title": "Monty Python's Flying Circus"}]}}

HANDLE = SessionHandle(
    id="sid-1", name="wikiracer-srv-1-abcd",
    live_url="https://api.steel.dev/v1/sessions/sid-1/player?interactive=false&hideOverlay=true",
    session_timeout_ms=900_000)


class Clock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class Resp:
    def __init__(self, body: bytes, status: int = 200):
        self._body, self.status = body, status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --------------------------------------------------------------------------- canonicalize


def test_canonicalize_follows_normalization_then_redirects(monkeypatch):
    monkeypatch.setattr(race, "http_get_json", lambda url, timeout=None: QUERY)
    got = race.canonicalize(["Snakes", "WWII", "barack obama", "Monty Python's Flying Circus", "Café"])
    assert got == {"Snakes": "Snake", "WWII": "World War II", "barack obama": "Barack Obama",
                   "Monty Python's Flying Circus": "Monty Python's Flying Circus",
                   "Café": "Coffeehouse"}


def test_canonicalize_says_none_for_missing_and_non_article_pages(monkeypatch):
    # The read view of a missing article carries a canonical link that repeats the typo
    # (verified), so the HTML alone would "resolve" a typo to itself. The API says missing.
    monkeypatch.setattr(race, "http_get_json", lambda url, timeout=None: QUERY)
    assert race.canonicalize(["NotARealArticleXyzzy", "Talk:Cat"]) == {
        "NotARealArticleXyzzy": None, "Talk:Cat": None}


def test_canonicalize_is_one_request_that_asks_for_redirects(monkeypatch):
    urls: list[str] = []

    def fake(url, timeout=None):
        urls.append(url)
        return {"query": {"pages": [{"pageid": 6678, "ns": 0, "title": "Cat"},
                                    {"pageid": 4269567, "ns": 0, "title": "Dog"}]}}

    monkeypatch.setattr(race, "http_get_json", fake)
    assert race.canonicalize(["Cat", "Dog"]) == {"Cat": "Cat", "Dog": "Dog"}
    assert len(urls) == 1
    q = parse_qs(urlparse(urls[0]).query)
    assert q["action"] == ["query"] and q["titles"] == ["Cat|Dog"]
    assert q["redirects"] == ["1"] and q["formatversion"] == ["2"]


def test_canonicalize_refuses_a_title_that_would_split_the_batch():
    with pytest.raises(ValueError):
        race.canonicalize(["Cat|Dog"])


# --------------------------------------------------------------------------- http


def test_http_get_sends_a_descriptive_user_agent_and_a_timeout(monkeypatch):
    seen: dict = {}

    def fake(req, timeout=None, context=None):
        seen.update(ua=req.get_header("User-agent"), timeout=timeout, context=context)
        return Resp(b"<html>ok</html>")

    monkeypatch.setattr(race.urllib.request, "urlopen", fake)
    assert race.http_get("https://en.wikipedia.org/wiki/Cat") == "<html>ok</html>"
    assert "WikiRacer" in seen["ua"]
    assert seen["timeout"] and seen["context"] is not None


def test_a_429_is_an_error_with_its_status_never_a_body_to_parse(monkeypatch):
    # CLAUDE.md rule 8: an unchecked 429 body became an empty move set. Twice.
    def fake(req, timeout=None, context=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"slow"))

    monkeypatch.setattr(race.urllib.request, "urlopen", fake)
    with pytest.raises(race.WikiError) as info:
        race.http_get("https://en.wikipedia.org/wiki/Cat")
    assert info.value.status == 429


def test_a_network_failure_is_a_wiki_error_without_a_status(monkeypatch):
    def fake(req, timeout=None, context=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(race.urllib.request, "urlopen", fake)
    with pytest.raises(race.WikiError) as info:
        race.http_get("https://en.wikipedia.org/wiki/Cat")
    assert info.value.status is None


def test_non_json_from_the_api_is_a_wiki_error(monkeypatch):
    monkeypatch.setattr(race, "http_get", lambda url, timeout=None: "<html>captive portal</html>")
    with pytest.raises(race.WikiError):
        race.http_get_json("https://en.wikipedia.org/w/api.php?action=query")


def test_ca_fallback_applies_only_when_python_has_no_bundle():
    # python.org's macOS Python ships none: cafile=None, capath=None (verified on this machine).
    bare = ssl.DefaultVerifyPaths(None, None, "SSL_CERT_FILE", "/nope/cert.pem", "SSL_CERT_DIR", "/nope/certs")
    fine = ssl.DefaultVerifyPaths("/usr/lib/ssl/cert.pem", None, "SSL_CERT_FILE", "/usr/lib/ssl/cert.pem",
                                  "SSL_CERT_DIR", "/nope")

    def exists(p):
        return p in ("/etc/ssl/cert.pem", "/usr/lib/ssl/cert.pem")

    assert race.fallback_cafile(bare, exists=exists, env={}) == "/etc/ssl/cert.pem"
    assert race.fallback_cafile(fine, exists=exists, env={}) is None
    assert race.fallback_cafile(bare, exists=exists, env={"SSL_CERT_FILE": "/mine.pem"}) is None


# --------------------------------------------------------------------------- SteelSource


def test_steel_source_stamps_arrival_when_navigation_finishes(monkeypatch):
    clock, order = Clock(100.0), []

    def navigate(name, url, wait_until="domcontentloaded"):
        order.append("navigate")
        clock.t = 100.8
        return {}

    def content(name):
        order.append("content")
        clock.t = 101.3
        return "<html>page</html>"

    monkeypatch.setattr(race.steel_client, "navigate", navigate)
    monkeypatch.setattr(race.steel_client, "content", content)
    src = race.SteelSource(HANDLE, started_at=100.0, clock=clock)
    assert src.goto("https://en.wikipedia.org/wiki/Cat") == ("<html>page</html>", 100.8)
    assert order == ["navigate", "content"]


def test_steel_source_will_not_command_a_session_past_its_lifetime(monkeypatch):
    # Probe trap 1: Steel silently starts a NEW session for a name it no longer knows.
    monkeypatch.setattr(race.steel_client, "navigate",
                        lambda *a, **k: pytest.fail("sent a command to an expired session"))
    clock = Clock(0.0)
    src = race.SteelSource(HANDLE, started_at=0.0, clock=clock)
    clock.t = 900.0
    with pytest.raises(steel_client.SteelSessionLost):
        src.goto("https://en.wikipedia.org/wiki/Cat")


def test_steel_source_open_starts_a_session_with_both_timeouts(monkeypatch):
    seen: dict = {}

    def start(session_timeout_ms=900_000, inactivity_timeout_ms=0, **kw):
        seen.update(session_timeout_ms=session_timeout_ms, inactivity_timeout_ms=inactivity_timeout_ms)
        return HANDLE

    monkeypatch.setattr(race.steel_client, "start_session", start)
    src = race.SteelSource(session_timeout_ms=900_000)
    src.open()
    assert seen == {"session_timeout_ms": 900_000, "inactivity_timeout_ms": 0}
    assert src.session_id == "sid-1" and src.live_url == HANDLE.live_url


def test_steel_source_close_always_reissues_the_stop_and_never_raises(monkeypatch):
    # Each close re-sends the (idempotent) stop BY NAME, so a session that a stray command
    # re-created under our name after an earlier stop is still torn down.
    calls: list[tuple[str, str | None]] = []

    def stop(name, session_id=None):
        calls.append((name, session_id))
        raise steel_client.SteelError("network down")

    monkeypatch.setattr(race.steel_client, "stop_session", stop)
    src = race.SteelSource(HANDLE, started_at=0.0)
    src.close()
    src.close()
    assert calls == [("wikiracer-srv-1-abcd", "sid-1")] * 2


def test_closing_an_unopened_steel_source_does_nothing(monkeypatch):
    monkeypatch.setattr(race.steel_client, "stop_session", lambda *a, **k: pytest.fail("stopped nothing"))
    race.SteelSource().close()


# --------------------------------------------------------------------------- HttpSource


def test_http_source_fetches_the_read_view(monkeypatch):
    monkeypatch.setattr(race, "http_get", lambda url, timeout=None: f"<html>{url}</html>")
    src = race.HttpSource(clock=Clock(7.0))
    src.open()
    assert src.goto("https://en.wikipedia.org/wiki/Cat") == ("<html>https://en.wikipedia.org/wiki/Cat</html>", 7.0)
    assert (src.session_id, src.live_url) == ("http", "")
    src.close()
