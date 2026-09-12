"""The LLM link picker. Lane B. PLAN.md §4.C, tool contract in §2.4.

The agent's whole policy is here: one forced tool call per hop over the legal
move set, with a deterministic fallback so a bad API response degrades the race
instead of ending it.

Read the `link_index` section below before touching the prompt. PLAN.md calls it
"the only silent-wrong-answer bug in the plan" and it is: if the number rendered
to the model is not the number we dereference, the agent moves to the link
*after* the one it reasoned about, on every hop, always in range, so nothing
errors and every test still passes.

Offline-testable: the client is injected, so tests mock it and never touch the
network.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Iterable, Sequence

import anthropic

from speedrun.types import Candidate, PickResult

MAX_TOKENS = 300


class NoCandidatesError(Exception):
    """No legal move exists from this page.

    Raised, never returned, and no API call is made. PLAN.md §4.C: v1 listed the
    empty list as a *fallback trigger* whose action was "pick the first
    candidate", which cannot hold. `race.py` catches this and returns
    `RaceResult(reason="dead_end")`.
    """


# --------------------------------------------------------------------------- #
# The tool contract. PLAN.md §2.4 — fixed shape, do not drift.
# --------------------------------------------------------------------------- #
CHOOSE_LINK_TOOL: dict[str, Any] = {
    "name": "choose_link",
    "description": "Pick exactly one candidate link to click next in the Wikipedia speedrun.",
    # Sibling of "name", NOT inside input_schema and NOT on tool_choice.
    # additionalProperties:False is inert on its own; "strict" enforces it.
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "link_index": {
                "type": "integer",
                "description": (
                    "The 0-BASED index of your chosen link, copied verbatim from "
                    "the number at the start of that line in the candidate list. "
                    "The list starts at 0."
                ),
            },
            "reason": {
                "type": "string",
                "description": "One short sentence (<=20 words) explaining the choice.",
            },
        },
        "required": ["link_index", "reason"],
        "additionalProperties": False,
    },
}

SYSTEM_PROMPT = (
    "You are playing a Wikipedia speedrun (wiki race). You start on one article "
    "and must reach a target article by moving only through links that appear in "
    "the article body. On each turn you will see the current article, the target "
    "article, the articles already visited this race, and a numbered list of "
    "candidate links from the current article. The list is 0-indexed: the first "
    "line is index 0. Pick exactly one link most likely to lead toward the target "
    "in the fewest hops, using your general knowledge of how topics connect on "
    "Wikipedia. When the target is far away or narrow, route through a broad hub "
    "article first (a country, a century, a field of study, a major organization) "
    "and then descend toward the target - do not pick a link merely because it is "
    "topically adjacent. Candidates you have already visited have been removed "
    "for you. Call `choose_link` with your pick and a single short reason."
)

# Errors that mean the request will never work: a bad key, a typo'd model, a
# malformed request. These RE-RAISE so cli.py can print one line and exit.
# PLAN.md §4.C: v1 funnelled every API exception into the fallback, which turns
# an expired key into a full 25-hop race of first-link picks on the projector.
FATAL = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
    anthropic.BadRequestError,
)

# Errors that mean "try again later, but we have a race to run". These take the
# deterministic fallback.
RETRYABLE = (
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
    anthropic.OverloadedError,
)


def model_params(model: str) -> dict[str, Any]:
    """Per-model request parameters. This function exists because of a real trap.

    PLAN.md §2.4 says "temperature=0 - REQUIRED". That is wrong twice over, both
    verified against the bundled Anthropic reference on 2026-09-12:

    1. On the `anthropic` 1.x SDK — which is what our own `anthropic>=1,<2` pin
       resolves to (1.5.0) — `temperature` is **not a keyword argument** of
       `messages.create()`. Passing it raises `TypeError`. It has to go through
       `extra_body`, which is merged into the request JSON as-is.
    2. Even via `extra_body`, **Claude Sonnet 5 rejects non-default sampling
       values** — and Sonnet 5 is exactly what FRONTEND.md §5.5's `hard` tier
       asks for. Haiku 4.5 accepts them (it is on the 4.6/4.5 line, which still
       does).

    So the `hard` tier cannot have determinism, and gets prompt-steering plus
    disabled thinking instead. Disabling thinking is the separate fix PLAN.md
    §2.4 already warns about: Sonnet 5 runs adaptive thinking when `thinking` is
    omitted, and `max_tokens` caps thinking + response TOGETHER, so 300 tokens
    truncates before the tool call lands and the fallback fires on every hop —
    a 100%-fallback bot that still looks like it is working.
    """
    if model.startswith("claude-haiku-4-5"):
        # Deterministic, and Haiku does not think by default.
        return {"extra_body": {"temperature": 0}}
    # Sonnet 5 and anything newer: no sampling params at all, thinking off.
    return {"thinking": {"type": "disabled"}}


def eligible(
    candidates: Sequence[Candidate],
    visited: Iterable[str] = (),
    banned_titles: Iterable[str] | None = None,
) -> list[Candidate]:
    """The moves we will actually offer, renumbered contiguously from 0.

    Filtering `visited` is STRUCTURAL, not advice. PLAN.md §4.C: v1 passed the
    visited list as prose with "avoid re-visiting unless it's clearly the best
    option", and the published benchmark for exactly this policy shape reports
    loops in roughly 61-66% of trajectories. With max_hops=25 a single 2-cycle
    eats the whole live demo.

    If filtering would empty the list we keep the unfiltered one — a dead end we
    can still move through beats no move at all.
    """
    drop = {v.casefold() for v in visited}
    drop |= {b.casefold() for b in (banned_titles or ())}
    keep = [c for c in candidates if c.title.casefold() not in drop]
    if not keep:
        keep = list(candidates)
    # Renumber so the rendered list is contiguous from 0. The SAME list is used
    # to render and to dereference, which is the invariant that matters.
    return [dataclasses.replace(c, index=i) for i, c in enumerate(keep)]


def render_candidates(shown: Sequence[Candidate]) -> str:
    """One line per move, numbered from `Candidate.index` VERBATIM.

    Never `enumerate(shown, 1)`. Never recompute the number. `eligible()` has
    already made `index` contiguous from 0, and this renders that same field, so
    the number the model reads is the number `parse_choice` dereferences.
    """
    return "\n".join(f"{c.index}. {c.text} -> {c.title}" for c in shown)


def build_user_prompt(
    current_title: str,
    target_title: str,
    visited: Sequence[str],
    shown: Sequence[Candidate],
    hop: int,
    max_hops: int,
    banned_titles: Iterable[str] | None = None,
) -> str:
    banned = sorted(banned_titles or ())
    parts = [
        f"Current article: {current_title}",
        f"Target article: {target_title}",
        f"Visited so far: {', '.join(visited) if visited else '(none yet)'}",
        f"Hop {hop} of {max_hops}.",
    ]
    if banned:
        parts.append(
            "Already tried from this page and it went nowhere: " + ", ".join(banned)
        )
    parts.append("")
    parts.append(f"Candidate links ({len(shown)}), 0-indexed:")
    parts.append(render_candidates(shown))
    return "\n".join(parts)


def parse_choice(
    response: Any, shown: Sequence[Candidate]
) -> tuple[Candidate, str] | None:
    """Pure validator. Returns (candidate, reason), or None to take the fallback.

    Kept separate from `choose_link` so the validation logic is unit-testable
    without mocking a whole API call — PLAN.md §4.C flags this as the one thing
    v1 got right here.
    """
    if getattr(response, "stop_reason", None) != "tool_use":
        return None  # refusal, max_tokens, end_turn — all degrade, none crash

    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != "choose_link":
            continue

        raw = getattr(block, "input", None)
        # Parse with json, never string-matching: model JSON escaping varies.
        if isinstance(raw, (str, bytes)):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                return None
        if not isinstance(raw, dict):
            return None

        idx = raw.get("link_index")
        if isinstance(idx, bool) or not isinstance(idx, int):
            return None
        # Dereference the SAME list we rendered.
        if not 0 <= idx < len(shown):
            return None

        reason = raw.get("reason")
        reason = reason.strip() if isinstance(reason, str) and reason.strip() else "(no reason given)"
        return shown[idx], reason

    return None


def fallback_pick(shown: Sequence[Candidate], why: str) -> PickResult:
    """Deterministic degradation. `shown` is already filtered, so the first entry
    is the first move that is not visited and not banned."""
    return PickResult(
        candidate=shown[0],
        reason=f"[fallback] {why}",
        was_fallback=True,
    )


def choose_link(
    client: Any,
    model: str,
    current_title: str,
    target_title: str,
    visited: Sequence[str],
    candidates: Sequence[Candidate],
    hop: int,
    max_hops: int,
    banned_titles: Iterable[str] | None = None,
) -> PickResult:
    """Pick the next hop. Never raises for an API problem; raises for a dead end."""
    if not candidates:
        raise NoCandidatesError(f"no legal moves from {current_title!r}")

    shown = eligible(candidates, visited, banned_titles)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[CHOOSE_LINK_TOOL],
            tool_choice={
                "type": "tool",
                "name": "choose_link",
                # Exactly one block, so parse_choice never has to choose.
                "disable_parallel_tool_use": True,
            },
            messages=[
                {
                    "role": "user",
                    "content": build_user_prompt(
                        current_title,
                        target_title,
                        visited,
                        shown,
                        hop,
                        max_hops,
                        banned_titles,
                    ),
                }
            ],
            **model_params(model),
        )
    except FATAL:
        # A bad key or a typo'd model is not a race condition — let it out.
        raise
    except RETRYABLE as exc:
        return fallback_pick(shown, type(exc).__name__)
    except anthropic.APIStatusError as exc:
        status = getattr(exc, "status_code", 0) or 0
        if status >= 500:
            return fallback_pick(shown, f"HTTP {status}")
        raise

    picked = parse_choice(response, shown)
    if picked is None:
        stop = getattr(response, "stop_reason", "?")
        return fallback_pick(shown, f"unusable response (stop_reason={stop})")

    candidate, reason = picked
    return PickResult(candidate=candidate, reason=reason, was_fallback=False)
