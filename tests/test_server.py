"""speedrun/server.py over real HTTP on an ephemeral port, with a fake race behind it.

The protocol is pinned to what Lane A's web/src/agent/sseFeed.ts actually does (read
2026-09-12): `POST /race {start, target, difficulty, find_target}` → `{id}` inside an 8 s
abort; `new EventSource("/events?race=<id>")` reading default `message` frames, deduped on
`seq`; `POST /race/<id>/go` with no body; `POST /stop` with no body and no race id.
"""

from __future__ import annotations

import http.client
import json
import threading
import time

import pytest
from fakes import FakeSource, FakeWiki, scripted

from speedrun import config, race, server
from speedrun import events as ev

ORIGIN = "http://localhost:5173"
WIKI = FakeWiki({"Cat": ["Ancient Egypt", "Dog"], "Ancient Egypt": ["Napoleon"], "Napoleon": [], "Dog": []})


def wait_until(pred, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.01)
    raise AssertionError("condition never became true")


class Harness:
    def __init__(self, make_source=None, factory_error: Exception | None = None, **manager_kw):
        self.make_source = make_source or (lambda: FakeSource(WIKI))
        self.factory_error = factory_error
        self.sources: list[FakeSource] = []
        self.params_seen: list[server.RaceParams] = []
        manager_kw.setdefault("first_connect_grace_s", 5.0)
        manager_kw.setdefault("drop_grace_s", 5.0)
        self.manager = server.RaceManager(self.factory, tiers=config.tiers(env={}), **manager_kw)
        self.httpd = server.make_server(self.manager, host="127.0.0.1", port=0,
                                        health=lambda: {"anthropic_key": True, "steel": True})
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def factory(self, params, log, stop, go):
        self.params_seen.append(params)
        if self.factory_error:
            raise self.factory_error
        src = self.make_source()
        self.sources.append(src)
        picker, _ = scripted("Ancient Egypt")
        return race.AgentRace(params.start, params.target, model=params.model, max_hops=params.max_hops,
                              use_find_target=params.use_find_target, source=src, log=log,
                              rules=WIKI.rules(), resolve_titles=WIKI.resolve_titles, picker=picker,
                              stop=stop, go=go, go_timeout_s=5.0)

    def request(self, method, path, body=None, headers=None, raw: bytes | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        hdrs = {"Origin": ORIGIN, **(headers or {})}
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
        if data is not None:
            hdrs.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        is_json = (resp.getheader("Content-Type") or "").startswith("application/json")
        return resp.status, resp.msg, (json.loads(payload) if payload and is_json else payload)

    def close(self):
        self.httpd.shutdown()
        self.manager.shutdown()
        self.httpd.server_close()


class SSE:
    """A minimal EventSource: reads `id:` / `data:` frames off the wire."""

    def __init__(self, port: int, race_id: str, last_event_id: int | None = None):
        self.conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {"Origin": ORIGIN, "Accept": "text/event-stream"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        self.conn.request("GET", f"/events?race={race_id}", headers=headers)
        self.resp = self.conn.getresponse()
        self.frames: list[list[str]] = []

    def next_event(self) -> dict:
        lines: list[str] = []
        while True:
            raw = self.resp.fp.readline()
            if not raw:
                raise EOFError("stream closed")
            line = raw.decode("utf-8").rstrip("\r\n")
            if line:
                lines.append(line)
                continue
            if not lines:
                continue
            self.frames.append(lines)
            data = [ln[5:].lstrip() for ln in lines if ln.startswith("data:")]
            lines = []
            if data:
                return json.loads("\n".join(data))

    def until(self, kind: str) -> list[dict]:
        out = []
        while True:
            e = self.next_event()
            out.append(e)
            if e["t"] == kind:
                return out

    def close(self):
        # For an HTTP/1.0 response, http.client hands the socket to the RESPONSE object, so
        # conn.close() alone leaves the TCP connection open and the server never sees it go.
        self.resp.close()
        self.conn.close()


@pytest.fixture
def h():
    harness = Harness()
    yield harness
    harness.close()


def start_race(h: Harness, **overrides) -> str:
    body = {"start": "Cat", "target": "Napoleon", "difficulty": "medium", "find_target": True, **overrides}
    status, _, data = h.request("POST", "/race", body)
    assert status == 201, data
    return data["id"]


def state_of(h: Harness, rid: str) -> str | None:
    run = h.manager.get(rid)
    return run.state if run else None


# --------------------------------------------------------------------------- the happy path


def test_health_reports_the_prerequisites(h):
    status, _, data = h.request("GET", "/health")
    assert status == 200
    assert (data["ok"], data["anthropic_key"], data["steel"], data["race"]) == (True, True, True, None)


def test_a_full_race_over_http(h):
    rid = start_race(h)
    sse = SSE(h.port, rid)
    assert sse.resp.status == 200
    assert sse.resp.getheader("Content-Type").startswith("text/event-stream")
    assert sse.resp.getheader("Cache-Control") == "no-cache"
    assert sse.resp.getheader("Access-Control-Allow-Origin") == ORIGIN
    ready = sse.next_event()
    assert (ready["t"], ready["seq"]) == ("ready", 1)
    assert h.request("POST", f"/race/{rid}/go")[0] == 200
    events = [ready] + sse.until("done")
    assert [e["t"] for e in events] == ["ready", "thinking", "pick", "arrive",
                                        "thinking", "pick", "arrive", "done"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    for e in events:
        ev.validate(e)
    assert events[-1]["reason"] == "won"
    sse.close()


def test_frames_are_plain_message_events_with_ids(h):
    # sseFeed.ts listens with `onmessage`, which never fires for a named `event:` frame.
    rid = start_race(h)
    sse = SSE(h.port, rid)
    sse.next_event()
    frame = sse.frames[-1]
    assert not any(line.startswith("event:") for line in frame)
    assert "id: 1" in frame
    sse.close()


def test_a_late_subscriber_gets_the_whole_log_replayed(h):
    # FRONTEND.md §2.7: the browser subscribes AFTER POST /race; without replay it would miss
    # `ready` and hang in arming.
    rid = start_race(h)
    wait_until(lambda: state_of(h, rid) == "ready")
    sse = SSE(h.port, rid)
    assert sse.next_event()["t"] == "ready"
    sse.close()


def test_last_event_id_resumes_instead_of_replaying(h):
    rid = start_race(h)
    wait_until(lambda: state_of(h, rid) == "ready")
    h.request("POST", f"/race/{rid}/go")
    wait_until(lambda: state_of(h, rid) == "done")
    sse = SSE(h.port, rid, last_event_id=3)
    assert sse.next_event()["seq"] == 4
    sse.close()


def test_difficulty_sets_the_model_and_find_target(h):
    start_race(h, difficulty="easy", find_target=None)
    assert (h.params_seen[-1].model, h.params_seen[-1].use_find_target) == ("claude-haiku-4-5", False)
    start_race(h, difficulty="hard")
    assert (h.params_seen[-1].model, h.params_seen[-1].use_find_target) == ("claude-sonnet-5", True)
    start_race(h, difficulty="medium", find_target=False)  # an explicit flag wins over the tier
    assert h.params_seen[-1].use_find_target is False


# --------------------------------------------------------------------------- the gun


def test_post_race_answers_before_arming_finishes():
    # sseFeed.ts aborts POST /race after 8 s; a cold start plus the first page must not block it.
    release = threading.Event()

    class SlowSource(FakeSource):
        def open(self):
            release.wait(5)
            super().open()

    h = Harness(make_source=lambda: SlowSource(WIKI))
    try:
        t = time.monotonic()
        rid = start_race(h)
        assert time.monotonic() - t < 1.0
        # Not ready: a GO now would start the clock on a browser that isn't there yet, and
        # POST /go must never create one synchronously (FRONTEND.md §8 trap 4).
        assert h.request("POST", f"/race/{rid}/go")[0] == 409
    finally:
        release.set()
        h.close()


def test_go_is_404_for_an_unknown_race(h):
    assert h.request("POST", "/race/nope/go")[0] == 404


def test_events_is_404_for_an_unknown_race(h):
    assert h.request("GET", "/events?race=nope")[0] == 404


def test_the_race_id_current_means_the_current_race(h):
    # sseFeed.ts falls back to the literal "current" if POST /race returns no id.
    start_race(h)
    sse = SSE(h.port, "current")
    assert sse.next_event()["t"] == "ready"
    sse.close()


# --------------------------------------------------------------------------- stopping


def test_stop_releases_the_browser_and_is_idempotent(h):
    rid = start_race(h)
    wait_until(lambda: state_of(h, rid) == "ready")
    assert h.request("POST", "/stop")[0] == 200
    wait_until(lambda: h.sources[-1].closed)
    assert state_of(h, rid) == "stopped"
    assert h.request("POST", "/stop")[0] == 200


def test_a_new_race_stops_the_old_one(h):
    first = start_race(h)
    wait_until(lambda: state_of(h, first) == "ready")
    second = start_race(h)
    assert second != first
    wait_until(lambda: h.sources[0].closed)
    assert h.request("GET", f"/events?race={first}")[0] == 404


def test_a_dropped_stream_stops_the_race():
    # FRONTEND.md §2.7: a reload drops the stream, so the server stops its own run, because a
    # leaked Steel session is the one unacceptable outcome.
    h = Harness(drop_grace_s=0.3)
    try:
        rid = start_race(h)
        sse = SSE(h.port, rid)
        sse.next_event()
        sse.close()
        wait_until(lambda: h.sources[-1].closed, timeout=5)
        assert state_of(h, rid) == "stopped"
    finally:
        h.close()


def test_a_race_nobody_subscribes_to_is_stopped():
    h = Harness(first_connect_grace_s=0.3)
    try:
        rid = start_race(h)
        wait_until(lambda: bool(h.sources) and h.sources[-1].closed, timeout=5)
        assert state_of(h, rid) == "stopped"
    finally:
        h.close()


def test_a_setup_problem_reaches_the_page_as_a_fatal_error():
    # e.g. no ANTHROPIC_API_KEY: say so on screen instead of hanging in arming for 20 s.
    h = Harness(factory_error=config.ConfigError("ANTHROPIC_API_KEY is not set."))
    try:
        rid = start_race(h)
        events = SSE(h.port, rid).until("done")
        assert events[-2]["t"] == "error" and events[-2]["fatal"] is True
        assert events[-1]["reason"] == "error" and "ANTHROPIC_API_KEY" in events[-1]["message"]
    finally:
        h.close()


# --------------------------------------------------------------------------- the browser's rules


def test_json_posts_pass_the_cors_preflight(h):
    status, headers, _ = h.request("OPTIONS", "/race", headers={
        "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert status == 204
    assert headers.get("Access-Control-Allow-Origin") == ORIGIN
    assert "POST" in headers.get("Access-Control-Allow-Methods")
    assert "content-type" in headers.get("Access-Control-Allow-Headers").lower()


def test_a_page_on_another_origin_cannot_start_a_race(h):
    # Any page the user visits can POST to 127.0.0.1, and a race spends Steel and Anthropic
    # credit. Only the app's own origins may.
    status, _, _ = h.request("POST", "/race", {"start": "Cat", "target": "Napoleon"},
                             headers={"Origin": "https://evil.example"})
    assert status == 403
    assert h.params_seen == []


def test_bad_bodies_are_400(h):
    assert h.request("POST", "/race", {"start": "Cat"})[0] == 400
    assert h.request("POST", "/race", {"start": "Cat", "target": "Dog", "difficulty": "impossible"})[0] == 400
    assert h.request("POST", "/race", raw=b"{not json")[0] == 400
    assert h.params_seen == []


def test_the_server_only_listens_on_loopback():
    assert server.DEFAULT_HOST == "127.0.0.1" and server.DEFAULT_PORT == 8848
