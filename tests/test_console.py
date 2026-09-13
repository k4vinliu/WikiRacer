"""speedrun/console.py: Lane C's debugging view, one line per agent event (display.py is dead)."""

from __future__ import annotations

import io

from speedrun import console
from speedrun import events as ev

BODIES = [
    ev.ready(session_id="sid-1", live_url="https://api.steel.dev/v1/sessions/sid-1/player?interactive=false"),
    ev.thinking(article="Cat", n_candidates=472),
    ev.pick(from_="Cat", to="Ancient Egypt", anchor_text="ancient Egyptians", reason="A hub.", was_fallback=False),
    ev.arrive(article="Ancient Egypt", hop=1),
    ev.done(reason="won", hops=2),
    ev.error(message="Loading 'Napoleon' failed; retrying once.", fatal=False),
]


def fmt(body: dict, at: int = 0) -> str:
    return console.format_event({"seq": 1, "at": at, **body})


def test_every_kind_formats_to_exactly_one_line():
    for body in BODIES:
        line = fmt(body)
        assert line and "\n" not in line, body["t"]


def test_the_time_is_seconds_since_the_gun():
    assert "2.50s" in fmt(ev.arrive(article="Brazil", hop=1), at=2500)


def test_a_pick_names_the_anchor_text_as_it_appeared_and_the_canonical_title():
    # PLAN.md §4.D's obligation: the anchor text is what proves the link was on the page, and
    # the title next to it shows where a redirect actually went.
    line = fmt(ev.pick(from_="Cat", to="Ancient Egypt", anchor_text="ancient Egyptians",
                       reason="A hub.", was_fallback=False))
    assert '"ancient Egyptians"' in line and "Ancient Egypt" in line and "A hub." in line


def test_matching_anchor_text_and_title_are_not_printed_twice():
    line = fmt(ev.pick(from_="Egypt", to="Napoleon", anchor_text="Napoleon", reason="On the page.",
                       was_fallback=False))
    assert line.count("Napoleon") == 1


def test_a_fallback_pick_is_flagged():
    line = fmt(ev.pick(from_="Cat", to="Dog", anchor_text="dogs", reason="[fallback] RateLimitError",
                       was_fallback=True))
    assert "FALLBACK" in line


def test_errors_and_done_show_their_message():
    assert "Steel is down" in fmt(ev.done(reason="error", hops=0, message="Steel is down"))
    assert "fatal" in fmt(ev.error(message="Anthropic rejected the API key", fatal=True))


def test_print_event_writes_one_line():
    buf = io.StringIO()
    console.print_event({"seq": 1, "at": 0, **BODIES[1]}, stream=buf)
    assert buf.getvalue().count("\n") == 1
