"""The agent's event stream, in Python. Lane C. FRONTEND.md §6.1.

This is the mirror of `web/src/agent/types.ts`, the one cross-lane contract. The server
emits these over SSE, and Lane A's `gameStore` adjudicates the race on them. If you edit a
field here and not there (or there and not here), the race silently stops adjudicating, so
`tests/test_events.py` parses types.ts and fails the build instead.

`at` is milliseconds since the gun (`POST /race/{id}/go`). Events logged before the gun
(`ready`, or an arming failure) carry `at: 0`. The referee adjudicates on `at`, never on
arrival order (FRONTEND.md §2.6 rule 1), so an event may be stamped with the moment the
thing HAPPENED, e.g. when the agent's page finished loading: `emit(..., at_s=...)`.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Iterator

Event = dict[str, Any]

# RaceReason minus "human_finished_first": `done` is terminal for the AGENT only.
DONE_REASONS = ("won", "hop_limit_reached", "dead_end", "error")

# kind -> {field: (python type, optional)}. Every event also carries seq, t and at.
FIELDS: dict[str, dict[str, tuple[type, bool]]] = {
    "ready": {"session_id": (str, False), "live_url": (str, False)},
    "thinking": {"article": (str, False), "n_candidates": (int, False)},
    "pick": {"from": (str, False), "to": (str, False), "anchor_text": (str, False),
             "reason": (str, False), "was_fallback": (bool, False)},
    "arrive": {"article": (str, False), "hop": (int, False)},
    "done": {"reason": (str, False), "hops": (int, False), "message": (str, True)},
    "error": {"message": (str, False), "fatal": (bool, False)},
}

_TS_KIND = {str: "string", int: "number", bool: "boolean"}


def ts_shape() -> dict[str, dict[str, tuple[str, bool]]]:
    """FIELDS spelled the way tests/test_events.py reads types.ts."""
    out = {}
    for kind, fields in FIELDS.items():
        shape = {"seq": ("number", False), "t": ("literal", False), "at": ("number", False)}
        shape.update({name: (_TS_KIND[typ], optional) for name, (typ, optional) in fields.items()})
        out[kind] = shape
    return out


def _is(value: Any, typ: type) -> bool:
    if typ is bool:
        return isinstance(value, bool)
    if typ is int:  # bool is an int in Python, but JSON would ship `true` to a TS number
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, typ)


def validate(e: Event) -> Event:
    """Raise ValueError unless `e` is exactly one of the §6.1 shapes. Returns `e`."""
    if not isinstance(e, dict):
        raise ValueError(f"an event is a dict, not {type(e).__name__}")
    kind = e.get("t")
    if kind not in FIELDS:
        raise ValueError(f"unknown event kind {kind!r}")
    if not _is(e.get("seq"), int) or e["seq"] < 1:
        raise ValueError(f"{kind}.seq must be an integer >= 1, got {e.get('seq')!r}")
    if not _is(e.get("at"), int) or e["at"] < 0:
        raise ValueError(f"{kind}.at must be an integer >= 0, got {e.get('at')!r}")
    fields = FIELDS[kind]
    extra = set(e) - set(fields) - {"seq", "t", "at"}
    if extra:
        raise ValueError(f"{kind} has unexpected field(s) {sorted(extra)}")
    for name, (typ, optional) in fields.items():
        if name not in e:
            if optional:
                continue
            raise ValueError(f"{kind}.{name} is required")
        if not _is(e[name], typ):
            raise ValueError(f"{kind}.{name} must be {typ.__name__}, got {e[name]!r}")
    if kind == "done" and e["reason"] not in DONE_REASONS:
        raise ValueError(f"done.reason must be one of {DONE_REASONS}, got {e['reason']!r}")
    if kind == "pick" and not e["anchor_text"].strip():
        # PLAN.md §4.D: the agent navigates instead of clicking, so the anchor text as it
        # appeared on the page is the evidence that the link existed. Blank is not evidence.
        raise ValueError("pick.anchor_text must name the link as it appeared on the page")
    return e


def _body(kind: str, **fields: Any) -> Event:
    body = {"t": kind, **fields}
    validate({"seq": 1, "at": 0, **body})
    return body


def ready(*, session_id: str, live_url: str) -> Event:
    return _body("ready", session_id=session_id, live_url=live_url)


def thinking(*, article: str, n_candidates: int) -> Event:
    return _body("thinking", article=article, n_candidates=n_candidates)


def pick(*, from_: str, to: str, anchor_text: str, reason: str, was_fallback: bool) -> Event:
    return _body("pick", **{"from": from_, "to": to, "anchor_text": anchor_text,
                            "reason": reason, "was_fallback": was_fallback})


def arrive(*, article: str, hop: int) -> Event:
    return _body("arrive", article=article, hop=hop)


def done(*, reason: str, hops: int, message: str | None = None) -> Event:
    fields: dict[str, Any] = {"reason": reason, "hops": hops}
    if message is not None:
        fields["message"] = message
    return _body("done", **fields)


def error(*, message: str, fatal: bool) -> Event:
    return _body("error", message=message, fatal=fatal)


class EventLog:
    """One race's events: append-only, thread-safe, replayable from any `seq`.

    Replay-on-connect is load-bearing (FRONTEND.md §2.7): the browser subscribes after
    POST /race, so without it the page misses `ready` and hangs in `arming` forever.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._events: list[Event] = []
        self._cond = threading.Condition()
        self._listeners: list[Callable[[Event], None]] = []
        self._t0: float | None = None
        self._closed = False

    @property
    def t0(self) -> float | None:
        return self._t0

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def events(self) -> list[Event]:
        with self._cond:
            return list(self._events)

    def mark_go(self) -> float:
        """Fire the gun. The first call wins; later calls return the same t0."""
        with self._cond:
            if self._t0 is None:
                self._t0 = self.clock()
            return self._t0

    def elapsed_s(self) -> float:
        return 0.0 if self._t0 is None else max(0.0, self.clock() - self._t0)

    def add_listener(self, fn: Callable[[Event], None]) -> None:
        """`fn(event)` runs synchronously on every emit, in order. Keep it quick."""
        with self._cond:
            self._listeners.append(fn)

    def emit(self, body: Event, at_s: float | None = None) -> Event | None:
        """Stamp `seq` and `at` onto an event body and append it. Returns None if the log is
        already closed: a late event from a race being stopped is dropped, not raised."""
        with self._cond:
            if self._closed:
                return None
            if self._t0 is None:
                at = 0
            else:
                stamp = self.clock() if at_s is None else at_s
                at = max(0, round((stamp - self._t0) * 1000))
            fields = {k: v for k, v in body.items() if k != "t"}
            e = validate({"seq": len(self._events) + 1, "t": body.get("t"), "at": at, **fields})
            self._events.append(e)
            self._cond.notify_all()
            for fn in list(self._listeners):
                try:
                    fn(e)
                except Exception:  # noqa: BLE001 - a broken debug printer must not end a race
                    pass
            return e

    def close(self) -> None:
        """No more events. Ends every follow() once it has drained."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def follow(self, after_seq: int = 0, heartbeat_s: float = 15.0) -> Iterator[Event | None]:
        """Every event with seq > after_seq (the replay), then each new one as it lands.

        Yields None after `heartbeat_s` of silence, so an SSE writer can send a ping and
        notice a client that went away. Returns once the log is closed and drained.
        """
        i = max(0, int(after_seq))
        while True:
            with self._cond:
                if i >= len(self._events) and not self._closed:
                    self._cond.wait(heartbeat_s)
                if i < len(self._events):
                    batch: list[Event] | None = self._events[i:]
                    i = len(self._events)
                elif self._closed:
                    return
                else:
                    batch = None
            if batch is None:
                yield None
            else:
                yield from batch
