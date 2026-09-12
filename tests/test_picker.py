"""Tests for speedrun/picker.py. Lane B. PLAN.md §4.C.

Zero network. The client is injected, so every test hands `choose_link` a fake
whose `messages.create` returns a canned object — and several tests assert the
call count, so a regression that starts reaching out would fail loudly rather
than quietly costing money on a projector.

The test that matters most is `test_rendered_list_is_zero_based`. PLAN.md calls
the index-base mismatch "the only silent-wrong-answer bug in the plan", and its
defining property is that nothing else catches it: the value is always in range,
so validation passes, the fallback never fires, and a suite built from
implementer-chosen canned indices agrees with the bug by construction.

Run: python3.11 -m pytest tests/test_picker.py -q
"""

from __future__ import annotations

# The anthropic 1.x SDK is built on httpx2, NOT httpx — that is one of the
# 0.x -> 1.x breaking changes. It ships as a transitive dependency, so there is
# nothing to add to requirements.txt; just import the right module.
import httpx2 as httpx
import pytest
import anthropic

from speedrun.picker import (
    CHOOSE_LINK_TOOL,
    MAX_TOKENS,
    SYSTEM_PROMPT,
    NoCandidatesError,
    build_user_prompt,
    choose_link,
    eligible,
    model_params,
    parse_choice,
    render_candidates,
)
from speedrun.types import Candidate

HAIKU = "claude-haiku-4-5"


# --------------------------------------------------------------------------- #
# Doubles
# --------------------------------------------------------------------------- #

class Block:
    def __init__(self, name="choose_link", inp=None, type_="tool_use"):
        self.type = type_
        self.name = name
        self.input = inp if inp is not None else {}


class Response:
    def __init__(self, stop_reason="tool_use", content=None):
        self.stop_reason = stop_reason
        self.content = content if content is not None else []


class FakeMessages:
    def __init__(self, result):
        self._result = result
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        if callable(self._result):
            return self._result(**kwargs)
        return self._result


class FakeClient:
    def __init__(self, result):
        self.messages = FakeMessages(result)


def tool_use(index: int, reason: str = "closer to the target") -> Response:
    return Response(content=[Block(inp={"link_index": index, "reason": reason})])


def cands(*titles: str) -> list[Candidate]:
    return [
        Candidate(
            index=i,
            text=t.lower(),
            title=t,
            href=f"https://en.wikipedia.org/wiki/{t.replace(' ', '_')}",
            is_redirect=False,
        )
        for i, t in enumerate(titles)
    ]


def call(client, candidates, **kw):
    return choose_link(
        client,
        kw.pop("model", HAIKU),
        kw.pop("current_title", "Cat"),
        kw.pop("target_title", "Napoleon"),
        kw.pop("visited", []),
        candidates,
        kw.pop("hop", 1),
        kw.pop("max_hops", 25),
        **kw,
    )


# --------------------------------------------------------------------------- #
# The index-base regression. Read the module docstring.
# --------------------------------------------------------------------------- #

def test_rendered_list_is_zero_based():
    c = FakeClient(tool_use(0))
    call(c, cands("Mammal", "Physics", "France"))
    prompt = c.messages.calls[0]["messages"][0]["content"]
    lines = [l for l in prompt.splitlines() if " -> " in l]
    assert lines[0].startswith("0."), f"first candidate line is not 0-based: {lines[0]!r}"
    assert [l.split(".", 1)[0] for l in lines] == ["0", "1", "2"]


def test_render_uses_the_index_field_not_a_fresh_enumeration():
    """If `render_candidates` re-enumerated, a non-contiguous list would silently
    be renumbered and the model's answer would dereference the wrong entry."""
    weird = [
        Candidate(index=7, text="a", title="Alpha", href="/wiki/Alpha", is_redirect=False),
        Candidate(index=9, text="b", title="Beta", href="/wiki/Beta", is_redirect=False),
    ]
    assert render_candidates(weird).splitlines() == ["7. a -> Alpha", "9. b -> Beta"]


def test_the_model_reads_the_same_list_we_dereference():
    """End to end: whatever index the model returns must resolve to the article
    named on that line of the prompt it was given."""
    captured: dict = {}

    def respond(**kwargs):
        captured["prompt"] = kwargs["messages"][0]["content"]
        return tool_use(2)

    c = FakeClient(respond)
    pick = call(c, cands("Mammal", "Physics", "France", "Spain"))
    line = next(
        l for l in captured["prompt"].splitlines() if l.startswith("2.")
    )
    assert pick.candidate is not None
    assert pick.candidate.title in line
    assert pick.candidate.title == "France"


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #

def test_valid_tool_use_is_accepted():
    pick = call(FakeClient(tool_use(1, "broad hub")), cands("Mammal", "Physics"))
    assert pick.was_fallback is False
    assert pick.candidate is not None and pick.candidate.title == "Physics"
    assert pick.reason == "broad hub"


def test_request_shape_matches_the_pinned_contract():
    c = FakeClient(tool_use(0))
    call(c, cands("Mammal"))
    kw = c.messages.calls[0]
    assert kw["model"] == HAIKU
    assert kw["max_tokens"] == MAX_TOKENS
    assert kw["system"] == SYSTEM_PROMPT
    assert kw["tools"] == [CHOOSE_LINK_TOOL]
    assert kw["tool_choice"]["type"] == "tool"
    assert kw["tool_choice"]["name"] == "choose_link"
    assert kw["tool_choice"]["disable_parallel_tool_use"] is True
    assert CHOOSE_LINK_TOOL["strict"] is True


def test_tool_input_may_arrive_as_a_json_string():
    """Model JSON escaping varies, so the input is parsed, never string-matched."""
    resp = Response(content=[Block(inp='{"link_index": 1, "reason": "ok"}')])
    pick = call(FakeClient(resp), cands("Mammal", "Physics"))
    assert pick.was_fallback is False
    assert pick.candidate is not None and pick.candidate.title == "Physics"


# --------------------------------------------------------------------------- #
# Model-specific request params. The trap this project actually hit.
# --------------------------------------------------------------------------- #

def test_haiku_gets_temperature_through_extra_body_not_a_kwarg():
    """`temperature` is not a kwarg on the anthropic 1.x messages.create; it
    raises TypeError. Determinism has to go through extra_body."""
    p = model_params(HAIKU)
    assert p == {"extra_body": {"temperature": 0}}
    assert "temperature" not in p


def test_sonnet_gets_no_sampling_params_and_thinking_off():
    """Sonnet 5 rejects non-default sampling values, and runs adaptive thinking
    when `thinking` is omitted — which would eat the 300-token budget before the
    tool call landed and fire the fallback on every hop."""
    p = model_params("claude-sonnet-5")
    assert p == {"thinking": {"type": "disabled"}}
    assert "extra_body" not in p


def test_no_call_ever_passes_temperature_as_a_keyword():
    for model in (HAIKU, "claude-sonnet-5"):
        c = FakeClient(tool_use(0))
        call(c, cands("Mammal"), model=model)
        assert "temperature" not in c.messages.calls[0]


# --------------------------------------------------------------------------- #
# Degradation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "resp,label",
    [
        (Response(content=[Block(inp={"link_index": 99, "reason": "x"})]), "out of range"),
        (Response(content=[Block(inp={"link_index": -1, "reason": "x"})]), "negative"),
        (Response(stop_reason="refusal", content=[]), "refusal"),
        (Response(stop_reason="max_tokens", content=[]), "max_tokens"),
        (Response(stop_reason="end_turn", content=[]), "no tool call"),
        (Response(content=[Block(name="something_else", inp={"link_index": 0})]), "wrong tool"),
        (Response(content=[Block(inp={"reason": "no index"})]), "missing index"),
        (Response(content=[Block(inp={"link_index": "1", "reason": "x"})]), "string index"),
        (Response(content=[Block(inp={"link_index": True, "reason": "x"})]), "bool index"),
        (Response(content=[Block(inp="not json at all")]), "unparseable input"),
    ],
)
def test_unusable_responses_fall_back(resp, label):
    pick = call(FakeClient(resp), cands("Mammal", "Physics"))
    assert pick.was_fallback is True, label
    assert pick.candidate is not None
    assert pick.reason.startswith("[fallback]")


def _status_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls("boom", response=response, body=None)


@pytest.mark.parametrize(
    "exc",
    [
        anthropic.APITimeoutError(httpx.Request("POST", "https://api.anthropic.com")),
        anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")),
        _status_error(anthropic.RateLimitError, 429),
        _status_error(anthropic.InternalServerError, 500),
    ],
)
def test_retryable_api_errors_fall_back(exc):
    pick = call(FakeClient(exc), cands("Mammal", "Physics"))
    assert pick.was_fallback is True
    assert pick.candidate is not None


@pytest.mark.parametrize(
    "cls,status",
    [
        (anthropic.AuthenticationError, 401),
        (anthropic.PermissionDeniedError, 403),
        (anthropic.NotFoundError, 404),
        (anthropic.BadRequestError, 400),
    ],
)
def test_fatal_api_errors_are_reraised(cls, status):
    """An expired key or a typo'd --model must stop the run, not produce a
    25-hop race of first-link picks on the projector."""
    with pytest.raises(cls):
        call(FakeClient(_status_error(cls, status)), cands("Mammal", "Physics"))


# --------------------------------------------------------------------------- #
# Dead ends
# --------------------------------------------------------------------------- #

def test_empty_candidates_raises_and_makes_no_api_call():
    c = FakeClient(tool_use(0))
    with pytest.raises(NoCandidatesError):
        call(c, [])
    assert c.messages.calls == [], "an empty move set must not cost an API call"


# --------------------------------------------------------------------------- #
# Filtering is structural, not advice
# --------------------------------------------------------------------------- #

def test_visited_titles_are_removed_and_indices_stay_contiguous():
    c = FakeClient(tool_use(0))
    call(c, cands("Mammal", "Physics", "France"), visited=["Physics"])
    prompt = c.messages.calls[0]["messages"][0]["content"]
    lines = [l for l in prompt.splitlines() if " -> " in l]
    assert "Physics" not in prompt.split("Candidate links", 1)[1]
    assert [l.split(".", 1)[0] for l in lines] == ["0", "1"]
    assert lines[0].endswith("Mammal") and lines[1].endswith("France")


def test_banned_titles_are_removed_too():
    c = FakeClient(tool_use(0))
    call(c, cands("Mammal", "Physics"), banned_titles={"Mammal"})
    prompt = c.messages.calls[0]["messages"][0]["content"]
    shown = prompt.split("Candidate links", 1)[1]
    assert "Mammal" not in shown and "Physics" in shown


def test_filtering_is_case_insensitive():
    assert [c.title for c in eligible(cands("Mammal", "Physics"), visited=["mammal"])] == [
        "Physics"
    ]


def test_unfiltered_list_is_kept_when_filtering_would_empty_it():
    """A dead end we can still move through beats no move at all."""
    got = eligible(cands("Mammal"), visited=["Mammal"])
    assert [c.title for c in got] == ["Mammal"]


def test_fallback_picks_the_first_eligible_not_the_first_raw():
    resp = Response(stop_reason="end_turn", content=[])
    pick = call(FakeClient(resp), cands("Mammal", "Physics"), visited=["Mammal"])
    assert pick.was_fallback is True
    assert pick.candidate is not None and pick.candidate.title == "Physics"


# --------------------------------------------------------------------------- #
# Prompt content
# --------------------------------------------------------------------------- #

def test_prompt_states_the_zero_index_convention_in_all_three_places():
    assert "0-indexed" in SYSTEM_PROMPT
    assert "0-BASED" in CHOOSE_LINK_TOOL["input_schema"]["properties"]["link_index"]["description"]
    prompt = build_user_prompt("Cat", "Napoleon", [], cands("Mammal"), 1, 25)
    assert "0-indexed" in prompt


def test_prompt_carries_the_race_state():
    prompt = build_user_prompt(
        "Cat", "Napoleon", ["Cat", "Mammal"], cands("Physics"), 3, 25,
        banned_titles={"France"},
    )
    assert "Current article: Cat" in prompt
    assert "Target article: Napoleon" in prompt
    assert "Cat, Mammal" in prompt
    assert "Hop 3 of 25" in prompt
    assert "France" in prompt


def test_empty_visited_reads_as_none_yet():
    assert "(none yet)" in build_user_prompt("Cat", "Napoleon", [], cands("X"), 1, 25)


# --------------------------------------------------------------------------- #
# parse_choice in isolation — the pure helper PLAN.md §4.C asks for
# --------------------------------------------------------------------------- #

def test_parse_choice_is_pure_and_needs_no_client():
    shown = cands("Mammal", "Physics")
    got = parse_choice(tool_use(1, "hub"), shown)
    assert got is not None
    candidate, reason = got
    assert candidate.title == "Physics" and reason == "hub"


def test_parse_choice_defaults_a_blank_reason():
    got = parse_choice(tool_use(0, "   "), cands("Mammal"))
    assert got is not None and got[1] == "(no reason given)"
