"""The seam between race.py (Lane C) and Lane B's real picker.py.

This module skips until Lane B's picker is merged. Only the Anthropic CLIENT is faked here;
the picker's filtering, numbering, prompt and parsing are Lane B's real code. The fake client
behaves like a model reading the prompt it was actually sent: it finds the line naming the
article it wants and answers with that line's number. The tests then check that the agent
follows that exact link. That is the end-to-end form of PLAN.md §4.C's silent-wrong-answer
bug, run on both lanes' real code.

What these catch, and what they can't (both checked by mutation on 2026-09-12): a picker that
renders from 1 but dereferences from 0 fails the two numbering tests here, as it does four of
Lane B's own. A slip in race.py's renumbering does NOT fail them. The picker renumbers
whatever it's handed and dereferences its own list, and race.py follows the returned
Candidate rather than an index, so that slip is harmless once the two are combined.
test_race.py still catches it in race.py alone.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("speedrun.picker", reason="Lane B's picker.py isn't merged yet")

import anthropic  # noqa: E402
import httpx2 as httpx  # noqa: E402  (the anthropic 1.x SDK is built on httpx2, not httpx)
from fakes import FakeSource, FakeWiki  # noqa: E402

from speedrun import events as ev  # noqa: E402
from speedrun import race  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
LINE = re.compile(r"^(\d+)\. (.*) -> (.*)$", re.M)


class ReadingModel:
    """Stands in for `client.messages`: picks by reading the numbered list it was sent."""

    def __init__(self, *wants: str):
        self.wants, self.prompts = list(wants), []

    def create(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        self.prompts.append(prompt)
        want = self.wants[len(self.prompts) - 1]
        line = next((m for m in LINE.finditer(prompt) if m.group(3) == want), None)
        assert line is not None, f"{want!r} is not in the list the model was shown"
        block = SimpleNamespace(type="tool_use", name="choose_link",
                                input={"link_index": int(line.group(1)), "reason": f"toward {want}"})
        return SimpleNamespace(stop_reason="tool_use", content=[block])


class FailingModel:
    def __init__(self, exc: Exception):
        self.exc = exc

    def create(self, **kwargs):
        raise self.exc


def api_error(cls, status: int):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


def agent(start, target, messages, *, wiki=None, source=None, rules=None, resolve=None):
    log = ev.EventLog()
    src = source or FakeSource(wiki)
    r = race.AgentRace(start, target, model="claude-haiku-4-5", max_hops=10, use_find_target=False,
                       source=src, log=log, rules=rules or wiki.rules(),
                       resolve_titles=resolve or wiki.resolve_titles, picker=race.llm_picker(),
                       client=SimpleNamespace(messages=messages))
    return r, log, src


def test_the_line_the_model_reads_is_the_link_the_agent_follows_on_a_real_page():
    fixture = (REPO / "tests" / "fixtures" / "python_programming_language.html").read_text(encoding="utf-8")
    guido = ('<html><head><link rel="canonical" href="https://en.wikipedia.org/wiki/Guido_van_Rossum">'
             '</head><body><div id="mw-content-text"><p>BDFL</p></div></body></html>')

    class FixtureSource(FakeSource):
        def goto(self, url):
            self.visits.append(url)
            return (guido if "Guido" in url else fixture), 0.0

    model = ReadingModel("Guido van Rossum")
    r, log, _ = agent("Python (programming language)", "Guido van Rossum", model,
                      source=FixtureSource(None), rules=race.lane_b_rules(),
                      resolve=lambda ts: {t: t for t in ts})
    result = r.run()
    assert result.won and result.hops == 1
    pick = next(e for e in log.events if e["t"] == "pick")
    assert (pick["to"], pick["was_fallback"]) == ("Guido van Rossum", False)
    assert LINE.search(model.prompts[0]).group(1) == "0"  # the list the model saw starts at 0


def test_numbering_stays_consistent_across_hops_through_both_lanes():
    # race.py drops visited titles and renumbers from 0; the picker filters and renumbers
    # again. Over several hops, the line the model picks must still be the link followed.
    wiki = FakeWiki({"A": ["B", "Q"], "B": ["A", "C", "D"], "C": [], "D": ["A", "B", "Z"], "Q": [], "Z": []})
    model = ReadingModel("B", "D", "Z")
    r, _, _ = agent("A", "Z", model, wiki=wiki)
    result = r.run()
    assert result.won and result.path == ["A", "B", "D", "Z"]
    assert [m.group(0) for m in LINE.finditer(model.prompts[1])] == ["0. C -> C", "1. D -> D"]


def test_a_bad_key_ends_the_race_with_one_readable_line():
    wiki = FakeWiki({"A": ["B"], "B": ["Z"], "Z": []})
    r, log, src = agent("A", "Z", FailingModel(api_error(anthropic.AuthenticationError, 401)), wiki=wiki)
    result = r.run()
    assert result.reason == "error" and "API key" in result.error
    assert [e["t"] for e in log.events][-2:] == ["error", "done"]
    assert src.closed


def test_a_rate_limit_becomes_a_flagged_fallback_not_the_end_of_the_race():
    wiki = FakeWiki({"A": ["Z"], "Z": []})
    r, log, _ = agent("A", "Z", FailingModel(api_error(anthropic.RateLimitError, 429)), wiki=wiki)
    assert r.run().won  # the fallback takes the first unvisited link, which here is the target
    pick = next(e for e in log.events if e["t"] == "pick")
    assert pick["was_fallback"] is True and pick["reason"].startswith("[fallback]")
