"""The bridge between the Python agent and the browser. Lane C. FRONTEND.md §2.3, §7.

Standard library only, with zero new dependencies: a ThreadingHTTPServer on 127.0.0.1:8848.
A plain HTTPServer would queue every request behind the open event stream; that one word is
the whole trick (FRONTEND.md §2.3). The protocol is exactly what Lane A's
web/src/agent/sseFeed.ts speaks:

    POST /race            {start, target, difficulty?, find_target?, max_hops?}
                          → 201 {id, events}. Answers at once. Arming (the Steel cold start,
                          parking on the start article) runs in the background.
    GET  /events?race=ID  Server-Sent Events. Replays the race's whole log, then streams it
                          live. Plain `message` frames (`id:` + `data:`), deduped client-side
                          on seq. Honours Last-Event-ID. ID may be "current".
    POST /race/ID/go      The gun: the server's clock starts when this arrives. 409 until
                          `ready`, so a GO can never create a browser synchronously
                          (FRONTEND.md §8 trap 4).
    POST /stop            Stop the current race and release its browser. Idempotent.
    GET  /health          {ok, anthropic_key, steel, ..., race}

One race at a time: a new POST /race stops the previous one. If a race's event stream drops
(a reload, a closed tab), the server stops that race itself after a short grace
(FRONTEND.md §2.7), because a leaked Steel session is the one unacceptable outcome. Only
pages served from this machine may drive it, because a race spends Steel and Anthropic credit.

    python3.11 -m speedrun.server [--page-source steel|http] [--picker llm|first]
"""

from __future__ import annotations

import argparse
import json
import secrets
import select
import signal
import socket
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterable, Mapping

from speedrun import config, console, race, steel_client
from speedrun import events as ev

DEFAULT_HOST = config.SERVER_HOST
DEFAULT_PORT = config.SERVER_PORT
SESSION_PREFIX = "wikiracer-srv"  # stop_leaked() only ever touches sessions with this prefix
MAX_BODY_BYTES = 64 * 1024
MAX_TITLE_CHARS = 300
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
SSE_POLL_S = 1.0    # how often an idle stream checks whether its client has gone
SSE_PING_S = 15.0   # keep-alive comment for anything between us and the browser


# =========================================================================== requests


class BadRequest(ValueError):
    pass


@dataclass(frozen=True)
class RaceParams:
    start: str
    target: str
    difficulty: str
    model: str
    use_find_target: bool
    max_hops: int


def parse_race_request(body: Any, tiers: Mapping[str, config.Tier]) -> RaceParams:
    if not isinstance(body, dict):
        raise BadRequest("the body must be a JSON object")

    def title(key: str) -> str:
        value = body.get(key)
        if not isinstance(value, str) or not value.strip():
            raise BadRequest(f"{key!r} must be a non-empty string")
        if len(value) > MAX_TITLE_CHARS:
            raise BadRequest(f"{key!r} is longer than {MAX_TITLE_CHARS} characters")
        return value.strip()

    start, target = title("start"), title("target")
    difficulty = body.get("difficulty") or "medium"
    if difficulty not in tiers:
        raise BadRequest(f"'difficulty' must be one of {sorted(tiers)}")
    tier = tiers[difficulty]
    find_target = body.get("find_target")
    if find_target is None:
        find_target = tier.use_find_target
    elif not isinstance(find_target, bool):
        raise BadRequest("'find_target' must be true or false")
    max_hops = body.get("max_hops")
    if max_hops is None:
        max_hops = config.DEFAULT_MAX_HOPS
    elif isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 1 <= max_hops <= 100:
        raise BadRequest("'max_hops' must be an integer from 1 to 100")
    return RaceParams(start, target, difficulty, tier.model, find_target, max_hops)


def origin_allowed(origin: str | None, extra: Iterable[str] = ()) -> bool:
    """Requests without an Origin (curl, the CLI) are fine. A browser page is allowed only if
    it's served from this machine, or was named with --allow-origin."""
    if not origin:
        return True
    if origin in extra:
        return True
    try:
        parts = urllib.parse.urlsplit(origin)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and (parts.hostname or "") in LOCAL_HOSTS


# =========================================================================== races


Factory = Callable[[RaceParams, ev.EventLog, threading.Event, threading.Event], Any]


class Run:
    """One race: its event log, its flags, and the thread that owns its browser."""

    def __init__(self, params: RaceParams, factory: Factory):
        self.id = secrets.token_hex(4)
        self.params = params
        self.log = ev.EventLog()
        self.stop = threading.Event()
        self.go = threading.Event()
        self.finished = threading.Event()
        self.state = "arming"  # arming → ready → racing → done | stopped
        self.agent: Any = None
        self.subscribers = 0
        self.ever_subscribed = False
        self.idle_since = time.monotonic()
        self.lock = threading.Lock()
        self._factory = factory
        self.log.add_listener(self._track)
        self.thread = threading.Thread(target=self._main, name=f"race-{self.id}", daemon=True)

    def _track(self, e: dict) -> None:
        with self.lock:
            if e["t"] == "ready" and self.state == "arming":
                self.state = "ready"
            elif e["t"] == "done" and self.state != "stopped":
                self.state = "done"

    def _main(self) -> None:
        try:
            self.agent = self._factory(self.params, self.log, self.stop, self.go)
            self.agent.run()
        except Exception as exc:  # noqa: BLE001 - e.g. no API key: tell the page, don't hang it
            message = race.describe(exc)
            self.log.emit(ev.error(message=message, fatal=True))
            self.log.emit(ev.done(reason="error", hops=0, message=message))
        finally:
            with self.lock:
                if self.state not in ("done", "stopped"):
                    self.state = "stopped" if self.stop.is_set() else "done"
            self.finished.set()


class RaceManager:
    def __init__(self, factory: Factory, *, tiers: Mapping[str, config.Tier] | None = None,
                 first_connect_grace_s: float = 30.0, drop_grace_s: float = 5.0,
                 on_event: Callable[[str, dict], None] | None = None,
                 on_note: Callable[[str], None] | None = None):
        self.factory = factory
        self.tiers = dict(tiers) if tiers is not None else config.tiers()
        self.first_connect_grace_s = first_connect_grace_s
        self.drop_grace_s = drop_grace_s
        self.on_event = on_event
        self.on_note = on_note or (lambda msg: None)
        self._lock = threading.Lock()
        self._current: Run | None = None
        self._closed = threading.Event()
        threading.Thread(target=self._watch, name="race-watchdog", daemon=True).start()

    @property
    def current(self) -> Run | None:
        with self._lock:
            return self._current

    def get(self, race_id: str | None) -> Run | None:
        run = self.current
        if run is not None and (race_id in (None, "", "current") or race_id == run.id):
            return run
        return None

    def describe_current(self) -> dict | None:
        run = self.current
        if run is None:
            return None
        p = run.params
        return {"id": run.id, "state": run.state, "start": p.start, "target": p.target,
                "difficulty": p.difficulty, "model": p.model}

    def create(self, params: RaceParams) -> Run:
        run = Run(params, self.factory)
        if self.on_event:
            run.log.add_listener(lambda e, rid=run.id: self.on_event(rid, e))
        with self._lock:
            old, self._current = self._current, run
        if old is not None:
            self._stop_run(old, "replaced by a new race")
        run.thread.start()
        return run

    def go(self, race_id: str) -> tuple[int, dict]:
        run = self.get(race_id)
        if run is None:
            return 404, {"error": "no such race"}
        with run.lock:
            if run.state == "racing":
                return 200, {"ok": True, "already_started": True}
            if run.state != "ready":
                return 409, {"error": f"the race is {run.state}, not ready"}
            run.state = "racing"
        run.log.mark_go()  # the gun: the server's t0 is the moment this request arrived
        run.go.set()
        return 200, {"ok": True}

    def stop(self, race_id: str | None = None, why: str = "stopped by the client") -> Run | None:
        run = self.get(race_id)
        if run is not None:
            self._stop_run(run, why)
        return run

    def _stop_run(self, run: Run, why: str) -> None:
        with run.lock:
            if run.stop.is_set():
                return
            run.stop.set()
            if not run.finished.is_set():
                run.state = "stopped"
        run.log.close()  # ends its event streams; late events from the race thread are dropped
        self.on_note(f"race {run.id}: {why}")

    def subscribe(self, run: Run) -> None:
        with run.lock:
            run.subscribers += 1
            run.ever_subscribed = True
            run.idle_since = time.monotonic()

    def unsubscribe(self, run: Run) -> None:
        with run.lock:
            run.subscribers -= 1
            run.idle_since = time.monotonic()

    def _watch(self) -> None:
        """FRONTEND.md §2.7: a race whose page has gone must not keep a cloud browser alive."""
        while not self._closed.wait(0.1):
            run = self.current
            if run is None or run.stop.is_set() or run.finished.is_set():
                continue
            with run.lock:
                idle = run.subscribers == 0
                grace = self.drop_grace_s if run.ever_subscribed else self.first_connect_grace_s
                overdue = time.monotonic() - run.idle_since > grace
            if idle and overdue:
                self._stop_run(run, "its event stream went away" if run.ever_subscribed
                               else "nobody subscribed to its events")

    def shutdown(self, join_timeout_s: float = 60.0) -> None:
        self._closed.set()
        run = self.current
        if run is None:
            return
        self._stop_run(run, "the server is shutting down")
        run.thread.join(join_timeout_s)
        if run.thread.is_alive():
            # Last resort: the race thread is wedged inside a Steel call. Stop its browser directly.
            handle = getattr(getattr(run.agent, "source", None), "handle", None)
            if handle is not None:
                try:
                    steel_client.stop_session(handle.name, session_id=handle.id)
                except steel_client.SteelError as e:
                    self.on_note(f"could not stop {handle.name} ({handle.id}): {e}")


# =========================================================================== HTTP


class AgentServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], manager: RaceManager, health: Callable[[], dict],
                 allowed_origins: Iterable[str] = (), verbose: bool = False):
        super().__init__(address, Handler)
        self.manager = manager
        self.health = health
        self.allowed_origins = tuple(allowed_origins)
        self.verbose = verbose


def make_server(manager: RaceManager, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *,
                health: Callable[[], dict] | None = None, allowed_origins: Iterable[str] = (),
                verbose: bool = False) -> AgentServer:
    return AgentServer((host, port), manager, health or dict, allowed_origins, verbose)


class Handler(BaseHTTPRequestHandler):
    server_version = "WikiRacer/1.0"
    protocol_version = "HTTP/1.0"  # one request per connection; an SSE response ends at close

    @property
    def app(self) -> AgentServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.app.verbose:
            sys.stderr.write(f"[http] {self.address_string()} {fmt % args}\n")

    # ------------------------------------------------------------------ plumbing

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if not origin:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin_allowed(origin, self.app.allowed_origins):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")

    def _json(self, status: int, obj: Any) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin_allowed(origin, self.app.allowed_origins):
            return True
        self._json(403, {"error": f"pages from {origin} may not drive the agent"})
        return False

    def _read_json(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise BadRequest("bad Content-Length") from None
        if length > MAX_BODY_BYTES:
            raise BadRequest("the body is too large")
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise BadRequest("the body is not valid JSON") from None

    # ------------------------------------------------------------------ routes

    def do_OPTIONS(self) -> None:  # the CORS preflight for JSON POSTs
        if not self._origin_ok():
            return
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Last-Event-ID")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._origin_ok():
            return
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/health":
            return self._health()
        if url.path == "/events":
            return self._events((query.get("race") or [None])[0])
        self._json(404, {"error": f"no route for GET {url.path}"})

    def do_POST(self) -> None:
        if not self._origin_ok():
            return
        url = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.split("/") if p]
        try:
            body = self._read_json()  # always drained: an unread body can reset the connection
            if parts == ["race"]:
                params = parse_race_request(body, self.app.manager.tiers)
                run = self.app.manager.create(params)
                return self._json(201, {"id": run.id, "events": f"/events?race={run.id}"})
            if len(parts) == 3 and parts[0] == "race" and parts[2] == "go":
                return self._json(*self.app.manager.go(parts[1]))
            if parts == ["stop"]:
                race_id = (urllib.parse.parse_qs(url.query).get("race") or [None])[0]
                if race_id is None and isinstance(body, dict):
                    race_id = body.get("race")
                run = self.app.manager.stop(race_id)
                return self._json(200, {"ok": True, "stopped": run.id if run else None})
        except BadRequest as e:
            return self._json(400, {"error": str(e)})
        self._json(404, {"error": f"no route for POST {url.path}"})

    def _health(self) -> None:
        info = dict(self.app.health())
        self._json(200, {"ok": True, "anthropic_key": bool(info.pop("anthropic_key", False)),
                         "steel": bool(info.pop("steel", False)), **info,
                         "race": self.app.manager.describe_current()})

    def _events(self, race_id: str | None) -> None:
        manager = self.app.manager
        run = manager.get(race_id)
        if run is None or run.log.closed:
            # 404 makes EventSource give up instead of reconnecting forever to a dead race.
            return self._json(404, {"error": "no such race (it may have been stopped or replaced)"})
        try:
            after = int(self.headers.get("Last-Event-ID") or 0)
        except ValueError:
            after = 0
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        manager.subscribe(run)
        try:
            self._send(b"retry: 1000\n\n")
            last_sent = time.monotonic()
            # Replay first (load-bearing: FRONTEND.md §2.7), then live.
            for e in run.log.follow(after_seq=after, heartbeat_s=SSE_POLL_S):
                if e is None:
                    if self._client_gone():
                        break
                    if time.monotonic() - last_sent >= SSE_PING_S:
                        self._send(b": ping\n\n")
                        last_sent = time.monotonic()
                    continue
                self._send(f"id: {e['seq']}\ndata: {json.dumps(e, separators=(',', ':'))}\n\n".encode("utf-8"))
                last_sent = time.monotonic()
        except OSError:  # BrokenPipe / ConnectionReset: the page went away
            pass
        finally:
            manager.unsubscribe(run)

    def _send(self, data: bytes) -> None:
        self.wfile.write(data)
        self.wfile.flush()

    def _client_gone(self) -> bool:
        """An EventSource never sends anything, so a readable socket means the peer closed it."""
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except (OSError, ValueError):
            return True


# =========================================================================== main


def build_factory(page_source: str, picker_kind: str, client: Any) -> Factory:
    def factory(params: RaceParams, log: ev.EventLog, stop: threading.Event, go: threading.Event):
        if picker_kind == "llm":
            if client is None:
                raise config.ConfigError("The agent has no working Anthropic client: ANTHROPIC_API_KEY is "
                                         "missing or was rejected. Fix .env and restart the server.")
            picker = race.llm_picker()
        else:
            picker = race.first_link_picker()
        if page_source == "steel":
            source = race.SteelSource(session_timeout_ms=config.DEFAULT_SESSION_TIMEOUT_MS,
                                      name_prefix=SESSION_PREFIX)
        else:
            source = race.HttpSource()
        return race.AgentRace(params.start, params.target, model=params.model, max_hops=params.max_hops,
                              use_find_target=params.use_find_target, source=source, log=log,
                              rules=race.lane_b_rules(), picker=picker, client=client, stop=stop, go=go)
    return factory


def _note(msg: str) -> None:
    print(f"[server] {msg}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3.11 -m speedrun.server",
                                 description="The WikiRacer agent server (Lane C). Open the app with ?agent=real.")
    ap.add_argument("--host", default=DEFAULT_HOST, help="keep this 127.0.0.1 (default)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--page-source", choices=("steel", "http"), default="steel",
                    help="http = FRONTEND.md §9.3 lever 2: no browser, same loop, extractor and LLM")
    ap.add_argument("--picker", choices=("llm", "first"), default="llm",
                    help="first = DEV ONLY: always the first unvisited link, no API key needed")
    ap.add_argument("--allow-origin", action="append", default=[], metavar="ORIGIN",
                    help="another page origin allowed to drive the agent")
    ap.add_argument("--no-preflight", action="store_true", help="skip the Anthropic and Steel checks")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every HTTP request")
    args = ap.parse_args(argv)

    config.load_env()
    health: dict[str, Any] = {"page_source": args.page_source, "picker": args.picker,
                              "models": {k: t.model for k, t in config.tiers().items()}, "detail": {}}
    client = None
    if args.picker == "llm":
        try:
            client = config.make_client()
            if not args.no_preflight:
                config.preflight_anthropic(client, {t.model for t in config.tiers().values()})
            health["anthropic_key"] = True
        except config.ConfigError as e:
            client = None
            health["anthropic_key"] = False
            health["detail"]["anthropic"] = str(e)
            _note(f"WARNING: {e}")
    if args.page_source == "steel":
        ok, detail = (True, "not checked (--no-preflight)") if args.no_preflight else config.preflight_steel()
        health["steel"], health["detail"]["steel"] = ok, detail
        if not ok:
            _note(f"WARNING: {detail}")
        try:
            leaked = steel_client.stop_leaked(SESSION_PREFIX)
            if leaked:
                _note(f"stopped {len(leaked)} session(s) left over from an earlier run: {', '.join(leaked)}")
        except steel_client.SteelError as e:
            _note(f"could not check for leftover Steel sessions: {e}")
    else:
        health["steel"] = False
        health["detail"]["steel"] = "not used (--page-source http)"

    manager = RaceManager(build_factory(args.page_source, args.picker, client),
                          on_event=lambda rid, e: console.print_event(e, prefix=f"{rid} "), on_note=_note)
    httpd = make_server(manager, args.host, args.port, health=lambda: health,
                        allowed_origins=args.allow_origin, verbose=args.verbose)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        _note(f"WARNING: listening on {args.host}: anyone who can reach it can spend your Steel and Anthropic credit")

    def _terminate(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _terminate)
    _note(f"agent server on http://{args.host}:{httpd.server_address[1]}. Page source: {args.page_source}, "
          f"picker: {args.picker}, models: {health['models']}. Open the app with ?agent=real. "
          "Ctrl+C stops it and releases the Steel session.")
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        _note("stopping: releasing the Steel session...")
    finally:
        manager.shutdown()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
