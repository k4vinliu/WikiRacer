"""speedrun/events.py — the Python mirror of web/src/agent/types.ts (FRONTEND.md §6.1).

The last two tests are the ones that matter most: they parse types.ts and assert both
files describe the same events. If you edit one and not the other, the race silently
stops adjudicating — these tests make it loudly stop building instead.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

from speedrun import events as ev

TYPES_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "agent" / "types.ts"


def _log(start: float = 0.0):
    now = [start]
    return ev.EventLog(clock=lambda: now[0]), now


# --------------------------------------------------------------------------- shapes


def test_every_event_kind_builds_a_valid_event():
    log, _ = _log()
    bodies = [
        ev.ready(session_id="s1", live_url="https://api.steel.dev/v1/sessions/s1/player"),
        ev.thinking(article="Cat", n_candidates=472),
        ev.pick(from_="Cat", to="Ancient Egypt", anchor_text="ancient Egypt",
                reason="A hub.", was_fallback=False),
        ev.arrive(article="Ancient Egypt", hop=1),
        ev.done(reason="won", hops=2),
        ev.done(reason="error", hops=0, message="Steel is down"),
        ev.error(message="retrying", fatal=False),
    ]
    for body in bodies:
        ev.validate(log.emit(body))


def test_pick_is_serialized_with_the_typescript_field_name_from():
    body = ev.pick(from_="Cat", to="Dog", anchor_text="dogs", reason="r", was_fallback=True)
    assert body["from"] == "Cat" and "from_" not in body


def test_validate_rejects_a_missing_field():
    with pytest.raises(ValueError, match="anchor_text"):
        ev.validate({"seq": 1, "t": "pick", "at": 0, "from": "A", "to": "B",
                     "reason": "r", "was_fallback": False})


def test_validate_rejects_an_unknown_kind_and_an_extra_field():
    with pytest.raises(ValueError):
        ev.validate({"seq": 1, "t": "teleport", "at": 0})
    with pytest.raises(ValueError, match="surprise"):
        ev.validate({"seq": 1, "t": "arrive", "at": 0, "article": "A", "hop": 1, "surprise": 1})


def test_validate_rejects_a_bool_where_a_number_belongs():
    # bool is a subclass of int in Python; JSON would ship `true` where TS expects a number.
    with pytest.raises(ValueError, match="hop"):
        ev.validate({"seq": 1, "t": "arrive", "at": 0, "article": "A", "hop": True})


def test_a_pick_without_anchor_text_is_refused():
    # PLAN.md §4.D: the agent navigates rather than clicks, so the anchor text is the
    # evidence that the link really existed. An empty one is not evidence.
    with pytest.raises(ValueError):
        ev.pick(from_="A", to="B", anchor_text="", reason="r", was_fallback=False)


def test_done_only_carries_agent_endings():
    with pytest.raises(ValueError):
        ev.done(reason="human_finished_first", hops=1)


# --------------------------------------------------------------------------- the log


def test_seq_counts_up_from_one():
    log, _ = _log()
    assert [log.emit(ev.error(message=str(i), fatal=False))["seq"] for i in range(4)] == [1, 2, 3, 4]


def test_at_is_zero_before_the_gun_and_milliseconds_since_it_after():
    log, now = _log(100.0)
    assert log.emit(ev.ready(session_id="s", live_url="u"))["at"] == 0
    log.mark_go()
    now[0] = 101.25
    assert log.emit(ev.thinking(article="Cat", n_candidates=3))["at"] == 1250


def test_at_can_be_stamped_with_when_it_happened_not_when_it_was_logged():
    # The referee adjudicates on `at` (FRONTEND.md §2.6 rule 1), and the agent's page
    # finished loading before we got round to logging it.
    log, now = _log()
    log.mark_go()
    now[0] = 5.0
    assert log.emit(ev.arrive(article="Brazil", hop=1), at_s=3.5)["at"] == 3500


def test_the_first_gun_wins():
    log, now = _log(1.0)
    log.mark_go()
    now[0] = 9.0
    log.mark_go()
    assert log.t0 == 1.0


def test_follow_replays_the_log_then_streams_live_events():
    log, _ = _log()
    log.emit(ev.ready(session_id="s", live_url="u"))
    seen: list[str] = []
    started = threading.Event()

    def consume():
        started.set()
        for e in log.follow(heartbeat_s=0.05):
            if e is None:
                continue
            seen.append(e["t"])
            if e["t"] == "done":
                return

    th = threading.Thread(target=consume)
    th.start()
    started.wait(1)
    log.emit(ev.thinking(article="Cat", n_candidates=1))
    log.emit(ev.done(reason="won", hops=1))
    th.join(2)
    assert not th.is_alive()
    assert seen == ["ready", "thinking", "done"]


def test_follow_resumes_after_a_last_event_id():
    log, _ = _log()
    for i in range(3):
        log.emit(ev.error(message=str(i), fatal=False))
    log.close()
    assert [e["seq"] for e in log.follow(after_seq=2) if e] == [3]


def test_follow_yields_heartbeat_slots_while_idle_and_ends_on_close():
    log, _ = _log()
    it = log.follow(heartbeat_s=0.01)
    assert next(it) is None
    log.close()
    assert list(it) == []


def test_emitting_after_close_is_dropped_not_raised():
    # The server closes a race's log on POST /stop while the race thread may be mid-hop.
    # A late `arrive` must not turn a clean stop into a crash.
    log, _ = _log()
    log.close()
    assert log.emit(ev.error(message="late", fatal=False)) is None
    assert log.events == []


def test_listeners_see_every_event_in_order():
    log, _ = _log()
    seen: list[int] = []
    log.add_listener(lambda e: seen.append(e["seq"]))
    for _ in range(3):
        log.emit(ev.error(message="x", fatal=False))
    assert seen == [1, 2, 3]


# --------------------------------------------------------------------------- parity with types.ts


def _strip_comments(src: str) -> str:
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", src, flags=re.S))


def _ts_agent_events(src: str) -> dict[str, dict[str, tuple[str, bool]]]:
    src = _strip_comments(src)
    union = re.search(r"export type AgentEvent\s*=(.*?)export ", src, re.S).group(1)
    out: dict[str, dict[str, tuple[str, bool]]] = {}
    for body in re.findall(r"\{([^{}]*)\}", union):
        fields: dict[str, tuple[str, bool]] = {}
        for part in re.split(r"[;\n]", body):
            m = re.match(r"\s*(\w+)(\?)?\s*:\s*(.+?)\s*$", part)
            if not m:
                continue
            name, optional, typ = m.group(1), bool(m.group(2)), m.group(3)
            if re.fullmatch(r'"[^"]*"', typ):
                kind = "literal"
            elif typ in ("number", "string", "boolean"):
                kind = typ
            else:
                kind = "string"  # Exclude<RaceReason, ...> is a union of string literals
            fields[name] = (kind, optional)
        out[re.search(r't\s*:\s*"(\w+)"', body).group(1)] = fields
    return out


def test_the_python_schema_matches_types_ts():
    assert _ts_agent_events(TYPES_TS.read_text(encoding="utf-8")) == ev.ts_shape()


def test_done_reasons_match_types_ts():
    src = _strip_comments(TYPES_TS.read_text(encoding="utf-8"))
    union = re.search(r"export type RaceReason\s*=([^;]*);", src).group(1)
    reasons = set(re.findall(r'"(\w+)"', union)) - {"human_finished_first"}
    assert reasons == set(ev.DONE_REASONS)
