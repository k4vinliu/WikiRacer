"""speedrun/steel_client.py, offline — `subprocess.run` is replaced by a scripted fake.

Every canned stdout below is VERBATIM from the 2026-09-12 probe (docs/steel-json-shapes.md),
with tokens redacted, not an imagined shape. Writing these against a guessed shape is how
v1 got `live_url` wrong: the real key is `liveUrl`, and it is not even the right URL.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from speedrun import steel_client as sc

SID = "4d04be8b-4e00-8022-b8fd-fad0b6aaae10"


def start_ok(argv):
    name = argv[argv.index("--session") + 1]
    return json.dumps({"data": {
        "connectUrl": f"wss://connect.steel.dev/?sessionId={SID}&token=<redacted>&apiKey=<redacted>",
        "id": SID, "liveUrl": f"https://app.steel.dev/sessions/{SID}", "mode": "cloud",
        "name": name, "remainingMs": 899002}, "success": True}) + "\n"


SESSIONS_GET_OK = json.dumps({"data": {
    "debugUrl": f"https://api.steel.dev/v1/sessions/{SID}/player", "id": SID,
    "sessionViewerUrl": f"https://app.steel.dev/sessions/{SID}", "status": "live",
    "timeout": 900000}, "success": True}) + "\n"
NAVIGATE_OK = ('{"data":{"title":"Guido van Rossum - Wikipedia",'
               '"url":"https://en.wikipedia.org/wiki/Guido_van_Rossum"},"success":true}\n')
WAIT_TIMED_OUT = '{"error":"Wait timed out after 3000ms","error_code":"internal_error","success":false}\n'
SESSIONS_LIVE = json.dumps({"data": [
    {"id": SID, "mode": "cloud", "name": "wikiracer-srv-1789253763-ab12", "status": "live",
     "viewerUrl": f"https://app.steel.dev/sessions/{SID}"},
    {"id": "other", "mode": "cloud", "name": "someone-elses-job", "status": "live",
     "viewerUrl": "https://app.steel.dev/sessions/other"}], "success": True}) + "\n"
DOCTOR_PASS = ('{"data":{"checks":[{"category":"auth","detail":{"key":"ste-<redacted>","source":"config"},'
               '"name":"API key configured (source: config)","status":"pass","transient":false},'
               '{"category":"auth","name":"API key valid","status":"pass","transient":false}],'
               '"overall":"pass"},"success":true}\n')
# Not verbatim: Chrome's about:blank document, which is what an auto-created session holds.
BLANK = '{"data":"<html><head></head><body></body></html>","success":true}\n'


def stop_ok(argv):
    name = argv[argv.index("--session") + 1]
    return json.dumps({"data": {"stoppedSessions": [name]}, "success": True}) + "\n"


class FakeRun:
    """Stands in for subprocess.run, scripted by (group, command): stdout, (exit, stdout),
    an exception to raise, or a callable taking argv."""

    def __init__(self, script):
        self.script = dict(script)
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        key = (argv[1], argv[2])
        if key not in self.script:
            raise AssertionError(f"unexpected steel call: {argv}")
        out = self.script[key]
        if callable(out) and not isinstance(out, BaseException):
            out = out(argv)
        if isinstance(out, BaseException):
            raise out
        code, stdout = out if isinstance(out, tuple) else (0, out)
        return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr="")


@pytest.fixture
def steel(monkeypatch):
    def install(script):
        fake = FakeRun(script)
        monkeypatch.setenv("STEEL_BIN", "/fake/bin/steel")
        monkeypatch.setattr(sc.subprocess, "run", fake)
        return fake
    return install


# --------------------------------------------------------------------------- start


def test_start_passes_both_timeouts_and_json(steel):
    fake = steel({("browser", "start"): start_ok, ("sessions", "get"): SESSIONS_GET_OK})
    sc.start_session(session_timeout_ms=900_000, inactivity_timeout_ms=0)
    argv, _ = fake.calls[0]
    assert argv[:3] == ["/fake/bin/steel", "browser", "start"]
    assert argv[argv.index("--session-timeout") + 1] == "900000"
    assert argv[argv.index("--inactivity-timeout") + 1] == "0"
    assert "--json" in argv


def test_live_url_is_the_frameable_player_not_the_dashboard(steel):
    steel({("browser", "start"): start_ok, ("sessions", "get"): SESSIONS_GET_OK})
    h = sc.start_session()
    assert h.live_url.startswith(f"https://api.steel.dev/v1/sessions/{SID}/player?")
    assert "interactive=false" in h.live_url and "hideOverlay=true" in h.live_url
    assert "app.steel.dev" not in h.live_url


def test_start_reports_id_generated_name_and_granted_timeout(steel):
    steel({("browser", "start"): start_ok, ("sessions", "get"): SESSIONS_GET_OK})
    h = sc.start_session(name_prefix="wikiracer-cli")
    assert h.id == SID
    assert h.name.startswith("wikiracer-cli-")
    assert h.session_timeout_ms == 900000


def test_generated_names_do_not_collide():
    # `browser start` ATTACHES to an existing name, so a reused name is a shared browser.
    assert len({sc.new_session_name("wikiracer-srv") for _ in range(50)}) == 50


def test_player_url_is_built_from_the_id_when_sessions_get_fails(steel):
    steel({("browser", "start"): start_ok,
           ("sessions", "get"): (1, '{"error":"boom","success":false}\n')})
    h = sc.start_session()
    assert h.live_url.startswith(f"https://api.steel.dev/v1/sessions/{SID}/player?")
    assert h.session_timeout_ms == 899002  # fell back to remainingMs


def test_a_start_without_an_id_stops_whatever_it_may_have_started(steel):
    fake = steel({("browser", "start"): '{"data":{},"success":true}\n', ("browser", "stop"): stop_ok})
    with pytest.raises(sc.SteelError):
        sc.start_session()
    assert any(argv[1:3] == ["browser", "stop"] for argv, _ in fake.calls)


# --------------------------------------------------------------------------- errors


def test_errors_are_read_from_stdout_not_stderr(steel):
    steel({("browser", "navigate"): (1, WAIT_TIMED_OUT)})
    with pytest.raises(sc.SteelError, match="Wait timed out after 3000ms") as info:
        sc.navigate("s", "https://en.wikipedia.org/wiki/Cat")
    assert info.value.exit_code == 1


def test_a_hung_cli_raises_steel_timeout(steel):
    steel({("browser", "content"): subprocess.TimeoutExpired(cmd="steel", timeout=45)})
    with pytest.raises(sc.SteelTimeout):
        sc.content("s")


def test_unparseable_stdout_is_an_error_even_with_exit_zero(steel):
    steel({("browser", "navigate"): (0, "definitely not json")})
    with pytest.raises(sc.SteelError):
        sc.navigate("s", "https://en.wikipedia.org/wiki/Cat")


def test_every_call_passes_json_and_a_timeout(steel):
    fake = steel({("browser", "start"): start_ok, ("sessions", "get"): SESSIONS_GET_OK,
                  ("browser", "navigate"): NAVIGATE_OK, ("browser", "stop"): stop_ok,
                  ("browser", "content"): json.dumps({"data": "<html>" + "x" * 4000 + "</html>",
                                                      "success": True})})
    h = sc.start_session()
    sc.navigate(h.name, "https://en.wikipedia.org/wiki/Cat")
    sc.content(h.name)
    sc.stop_session(h.name)
    for argv, kw in fake.calls:
        assert "--json" in argv, argv
        assert kw.get("timeout", 0) > 0, argv


# --------------------------------------------------------------------------- navigate / content


def test_navigate_returns_the_landed_title_and_url(steel):
    steel({("browser", "navigate"): NAVIGATE_OK})
    got = sc.navigate("s", "https://en.wikipedia.org/wiki/Guido_van_Rossum")
    assert got == {"title": "Guido van Rossum - Wikipedia",
                   "url": "https://en.wikipedia.org/wiki/Guido_van_Rossum"}


def test_navigate_waits_for_domcontentloaded_by_default(steel):
    fake = steel({("browser", "navigate"): NAVIGATE_OK})
    sc.navigate("s", "https://en.wikipedia.org/wiki/Python_(programming_language)")
    argv, _ = fake.calls[0]
    assert argv[3] == "https://en.wikipedia.org/wiki/Python_(programming_language)"
    assert argv[argv.index("--wait-until") + 1] == "domcontentloaded"


def test_content_returns_the_page_html(steel):
    html = "<html>" + "Café " * 500 + "</html>"
    steel({("browser", "content"): json.dumps({"data": html, "success": True})})
    assert sc.content("s") == html


def test_a_blank_page_means_the_session_was_lost(steel):
    # Probe trap 1: a command against a gone session silently starts a fresh one on about:blank.
    steel({("browser", "content"): BLANK})
    with pytest.raises(sc.SteelSessionLost):
        sc.content("s")


# --------------------------------------------------------------------------- stop / sessions / doctor


def test_stop_session_succeeds_quietly(steel):
    steel({("browser", "stop"): stop_ok})
    assert sc.stop_session("s") is None


def test_stop_session_falls_back_to_releasing_by_id(steel):
    fake = steel({("browser", "stop"): (1, '{"error":"daemon gone","success":false}\n'),
                  ("sessions", "release"): '{"data":{},"success":true}\n'})
    sc.stop_session("s", session_id=SID)
    assert fake.calls[-1][0][1:4] == ["sessions", "release", SID]


def test_stop_session_raises_when_nothing_worked(steel):
    steel({("browser", "stop"): (1, '{"error":"daemon gone","success":false}\n'),
           ("sessions", "release"): (1, '{"error":"api down","success":false}\n')})
    with pytest.raises(sc.SteelError):
        sc.stop_session("s", session_id=SID)


def test_list_sessions_parses_the_live_shape(steel):
    steel({("browser", "sessions"): SESSIONS_LIVE})
    names = [s["name"] for s in sc.list_sessions()]
    assert names == ["wikiracer-srv-1789253763-ab12", "someone-elses-job"]


def test_stop_leaked_only_touches_our_own_prefix(steel):
    fake = steel({("browser", "sessions"): SESSIONS_LIVE, ("browser", "stop"): stop_ok})
    assert sc.stop_leaked("wikiracer-srv") == ["wikiracer-srv-1789253763-ab12"]
    stopped = [argv[argv.index("--session") + 1] for argv, _ in fake.calls if argv[1:3] == ["browser", "stop"]]
    assert stopped == ["wikiracer-srv-1789253763-ab12"]


def test_doctor_reports_pass(steel):
    steel({("doctor", "--preflight"): DOCTOR_PASS})
    ok, detail = sc.doctor()
    assert ok is True


def test_doctor_reports_the_failing_check(steel):
    steel({("doctor", "--preflight"): json.dumps({"data": {"checks": [
        {"category": "auth", "name": "API key valid", "status": "fail", "transient": False}],
        "overall": "fail"}, "success": True})})
    ok, detail = sc.doctor()
    assert ok is False and "API key valid" in detail


# --------------------------------------------------------------------------- binary resolution


def test_steel_bin_prefers_the_env_override(monkeypatch):
    monkeypatch.setenv("STEEL_BIN", "/opt/steel")
    assert sc.steel_bin() == "/opt/steel"


def test_a_missing_cli_says_how_to_install_it(monkeypatch, tmp_path):
    monkeypatch.delenv("STEEL_BIN", raising=False)
    monkeypatch.setattr(sc, "native_bin", lambda: tmp_path / "no-steel-here")
    monkeypatch.setattr(sc.shutil, "which", lambda _name: None)
    with pytest.raises(sc.SteelNotInstalled, match="setup.steel.dev"):
        sc.steel_bin()
