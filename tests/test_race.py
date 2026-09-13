"""speedrun/race.py — the agent's loop, against fakes: no Steel, no LLM, no network.

FakeWiki (tests/fakes.py) is a tiny model of Wikipedia: a link graph plus redirects. Its
rules stand in for Lane B's links.py + wiki.py so that the LOOP is tested on its own.
The last test swaps Lane B's real rules in against the committed fixture; it skips until
their branch is merged.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fakes import FakeSource, FakeWiki, NoCandidates, scripted

from speedrun import events as ev
from speedrun import race
from speedrun.types import PickResult

REPO = Path(__file__).resolve().parents[1]


def make(wiki, start, target, picker=None, source=None, **kw):
    log = kw.pop("log", None) or ev.EventLog()
    src = source or FakeSource(wiki)
    r = race.AgentRace(start, target, model="claude-haiku-4-5", max_hops=kw.pop("max_hops", 25),
                       use_find_target=kw.pop("use_find_target", True), source=src, log=log,
                       rules=wiki.rules(), resolve_titles=wiki.resolve_titles,
                       picker=picker or scripted()[0], client=None, **kw)
    return r, log, src


def kinds(log) -> list[str]:
    return [e["t"] for e in log.events]


def last(log, t: str) -> dict:
    return [e for e in log.events if e["t"] == t][-1]


# --------------------------------------------------------------------------- winning


def test_a_visible_target_is_taken_without_asking_the_llm():
    wiki = FakeWiki({"Python (programming language)": ["Monty Python", "Guido van Rossum"],
                     "Guido van Rossum": [], "Monty Python": []})
    picker, calls = scripted()
    r, log, src = make(wiki, "Python (programming language)", "Guido van Rossum", picker)
    result = r.run()
    assert calls == []
    assert (result.won, result.winner, result.reason, result.hops) == (True, "bot", "won", 1)
    assert result.path == ["Python (programming language)", "Guido van Rossum"]
    assert kinds(log) == ["ready", "thinking", "pick", "arrive", "done"]
    assert last(log, "done")["reason"] == "won" and last(log, "done")["hops"] == 1
    assert src.closed


def test_easy_tier_does_not_look_ahead():
    wiki = FakeWiki({"A": ["Target"], "Target": []})
    picker, calls = scripted("Target")
    r, _, _ = make(wiki, "A", "Target", picker, use_find_target=False)
    assert r.run().won
    assert len(calls) == 1  # the LLM was asked even though the target was on the page


def test_arrival_uses_the_canonical_title_after_a_redirect():
    # The v1-killer: target typed as a redirect, reached through a redirect link.
    wiki = FakeWiki({"A": ["Snakes"], "Snake": []}, redirects={"Snakes": "Snake"})
    picker, _ = scripted("Snakes")
    r, log, _ = make(wiki, "A", "Snakes", picker)
    result = r.run()
    assert result.won and result.path == ["A", "Snake"]
    assert last(log, "arrive")["article"] == "Snake"


def test_the_pick_names_the_anchor_text_as_it_appeared_on_the_page():
    wiki = FakeWiki({"A": [("the snake family", "Snake")], "Snake": ["T"], "T": []})
    picker, _ = scripted("Snake")
    r, log, _ = make(wiki, "A", "T", picker)
    r.run()
    first_pick = [e for e in log.events if e["t"] == "pick"][0]
    assert (first_pick["from"], first_pick["to"], first_pick["anchor_text"]) == ("A", "Snake", "the snake family")


# --------------------------------------------------------------------------- what the picker sees


def test_the_picker_sees_unvisited_candidates_numbered_from_zero():
    # PLAN.md §4.C: the only silent-wrong-answer bug in the plan lives in this numbering.
    wiki = FakeWiki({"A": ["B"], "B": ["A", "C", "D"], "C": [], "D": ["Z"], "Z": []})
    picker, calls = scripted("B", "D")
    r, _, _ = make(wiki, "A", "Z", picker)
    assert r.run().won
    second = calls[1]
    assert [c.title for c in second["candidates"]] == ["C", "D"]
    assert [c.index for c in second["candidates"]] == [0, 1]
    assert second["visited"] == ["A", "B"]  # includes the start article
    assert second["hop"] == 2


def test_if_every_link_was_visited_the_picker_still_gets_the_list():
    wiki = FakeWiki({"A": ["B"], "B": ["A"], "T": []})
    picker, calls = scripted("B", "A", "B")
    r, _, _ = make(wiki, "A", "T", picker, max_hops=3)
    r.run()
    assert [c.title for c in calls[1]["candidates"]] == ["A"]
    assert [c.index for c in calls[1]["candidates"]] == [0]


def test_self_links_are_never_offered():
    wiki = FakeWiki({"A": ["A", "B"], "B": ["T"], "T": []})
    picker, calls = scripted("B")
    r, _, _ = make(wiki, "A", "T", picker)
    r.run()
    assert [c.title for c in calls[0]["candidates"]] == ["B"]


# --------------------------------------------------------------------------- the other endings


def test_hop_limit():
    wiki = FakeWiki({"A": ["B"], "B": ["A"], "T": []})
    picker, _ = scripted("B", "A", "B")
    r, log, src = make(wiki, "A", "T", picker, max_hops=3)
    result = r.run()
    assert (result.won, result.winner, result.reason, result.hops) == (False, "none", "hop_limit_reached", 3)
    assert last(log, "done")["reason"] == "hop_limit_reached" and last(log, "done")["hops"] == 3
    assert src.closed


def test_a_page_with_no_legal_moves_is_a_dead_end():
    wiki = FakeWiki({"A": ["B"], "B": [], "T": []})
    picker, _ = scripted("B")
    r, log, src = make(wiki, "A", "T", picker)
    result = r.run()
    assert (result.reason, result.hops) == ("dead_end", 1)
    assert last(log, "done")["reason"] == "dead_end"
    assert src.closed


def test_no_candidates_error_from_the_picker_is_a_dead_end():
    def choose(*args, **kwargs):
        raise NoCandidates()

    wiki = FakeWiki({"A": ["B"], "B": [], "T": []})
    r, log, _ = make(wiki, "A", "T", race.PickerFns(choose, NoCandidates))
    assert r.run().reason == "dead_end"
    assert last(log, "done")["reason"] == "dead_end"


def test_a_pick_of_none_is_a_dead_end():
    def choose(*args, **kwargs):
        return PickResult(candidate=None, reason="[fallback] nothing usable", was_fallback=True)

    wiki = FakeWiki({"A": ["B"], "B": [], "T": []})
    r, _, _ = make(wiki, "A", "T", race.PickerFns(choose, NoCandidates))
    assert r.run().reason == "dead_end"


def test_a_fatal_picker_error_is_reported_and_the_session_released():
    class AuthenticationError(Exception):
        pass

    def choose(*args, **kwargs):
        raise AuthenticationError("invalid x-api-key")

    wiki = FakeWiki({"A": ["B"], "B": [], "T": []})
    r, log, src = make(wiki, "A", "T", race.PickerFns(choose, NoCandidates))
    result = r.run()
    assert result.reason == "error" and "invalid x-api-key" in result.error
    assert last(log, "error")["fatal"] is True
    assert kinds(log)[-1] == "done" and last(log, "done")["reason"] == "error"
    assert "invalid x-api-key" in last(log, "done")["message"]
    assert src.closed


# --------------------------------------------------------------------------- arming


def test_a_missing_article_fails_before_ready_and_says_which():
    wiki = FakeWiki({"A": []})
    r, log, src = make(wiki, "A", "NotARealArticleXyzzy")
    result = r.run()
    assert result.reason == "error" and "NotARealArticleXyzzy" in result.error
    assert "ready" not in kinds(log)
    assert kinds(log)[-2:] == ["error", "done"]
    assert src.opened is False or src.closed


def test_start_equal_to_target_is_refused():
    wiki = FakeWiki({"Snake": []}, redirects={"Snakes": "Snake"})
    result = make(wiki, "Snakes", "Snake")[0].run()
    assert result.reason == "error" and "same article" in result.error


def test_it_does_not_move_before_the_gun():
    wiki = FakeWiki({"A": ["T"], "T": []})
    go = threading.Event()
    r, log, _ = make(wiki, "A", "T", go=go)
    th = threading.Thread(target=r.run)
    th.start()
    deadline = time.monotonic() + 2
    while "ready" not in kinds(log) and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.15)
    assert kinds(log) == ["ready"]
    log.mark_go()
    go.set()
    th.join(2)
    assert kinds(log)[-1] == "done"


def test_an_armed_race_that_never_starts_releases_its_session():
    wiki = FakeWiki({"A": ["T"], "T": []})
    r, log, src = make(wiki, "A", "T", go=threading.Event(), go_timeout_s=0.1)
    result = r.run()
    assert result.reason == "error"
    assert "thinking" not in kinds(log)
    assert src.closed


# --------------------------------------------------------------------------- stopping and failing


def test_stop_mid_race_ends_quietly_without_navigating_again():
    stop = threading.Event()

    def choose(client, model, current_title, target_title, visited, candidates, hop, max_hops, banned_titles=None):
        stop.set()  # the human won while the LLM was thinking
        return PickResult(candidate=candidates[0], reason="r", was_fallback=False)

    wiki = FakeWiki({"A": ["B"], "B": ["T"], "T": []})
    r, log, src = make(wiki, "A", "T", race.PickerFns(choose, NoCandidates), stop=stop, use_find_target=False)
    result = r.run()
    assert (result.won, result.error) == (False, "stopped")
    assert "done" not in kinds(log)  # the client stopped us; it already knows how it ended
    assert src.visits == ["A"]
    assert src.closed


def test_one_transient_navigation_failure_is_retried():
    wiki = FakeWiki({"A": ["T"], "T": []})
    src = FakeSource(wiki, fail_calls={2})  # call 1 parks on the start; call 2 is hop 1
    r, log, _ = make(wiki, "A", "T", source=src)
    assert r.run().won
    assert any(e["t"] == "error" and e["fatal"] is False for e in log.events)


def test_two_navigation_failures_in_a_row_end_the_race():
    wiki = FakeWiki({"A": ["T"], "T": []})
    src = FakeSource(wiki, fail_calls={2, 3})
    r, log, _ = make(wiki, "A", "T", source=src)
    result = r.run()
    assert result.reason == "error"
    assert last(log, "done")["reason"] == "error"
    assert src.closed


def test_arrive_is_stamped_when_the_page_finished_loading():
    now = [1000.0]
    log = ev.EventLog(clock=lambda: now[0])
    wiki = FakeWiki({"A": ["T"], "T": []})
    src = FakeSource(wiki, stamp=1002.5)  # the hop's page finished loading at t0 + 2.5 s
    r, log, _ = make(wiki, "A", "T", source=src, log=log, go=threading.Event())
    go_thread = threading.Thread(target=r.run)
    go_thread.start()
    while "ready" not in kinds(log):
        time.sleep(0.01)
    log.mark_go()  # t0 = 1000.0, set by the server's POST /go
    now[0] = 1004.0  # ...and the race logs everything later than it happened
    r.go.set()
    go_thread.join(2)
    assert last(log, "arrive")["at"] == 2500


# --------------------------------------------------------------------------- with Lane B's real rules


def test_the_real_extractor_takes_the_one_hop_win_on_the_fixture():
    pytest.importorskip("speedrun.links", reason="Lane B's links.py not merged yet")
    pytest.importorskip("speedrun.wiki", reason="Lane B's wiki.py not merged yet")
    fixture = (REPO / "tests" / "fixtures" / "python_programming_language.html").read_text(encoding="utf-8")
    guido = ('<html><head><link rel="canonical" href="https://en.wikipedia.org/wiki/Guido_van_Rossum">'
             '</head><body><div id="mw-content-text"><p>BDFL</p></div></body></html>')

    class FixtureSource(FakeSource):
        def goto(self, url):
            self.visits.append(url)
            return (guido if "Guido" in url else fixture), time.monotonic()

    picker, calls = scripted()
    log = ev.EventLog()
    r = race.AgentRace("Python (programming language)", "Guido van Rossum", model="claude-haiku-4-5",
                       max_hops=25, use_find_target=True, source=FixtureSource(None), log=log,
                       rules=race.lane_b_rules(), resolve_titles=lambda ts: {t: t for t in ts},
                       picker=picker, client=None)
    result = r.run()
    assert result.won and result.hops == 1 and calls == []
    assert last(log, "thinking")["n_candidates"] > 200
