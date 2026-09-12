"""Shared data types for the Wikipedia Speedrun bot.

Transcribed from PLAN.md Section 2.1. This module is FROZEN: every other package is
built against these shapes, so changing a field is a Section 2 contract amendment —
say so in the team chat and amend the log at the top of PLAN.md Section 2. Do not
just add the field.

Requires Python 3.10+ (`X | None` syntax).
"""

# Makes every annotation below a string at runtime, so this module imports cleanly on
# Python 3.9 too. Without it, `Candidate | None` is evaluated at class-creation time and
# raises `TypeError: unsupported operand type(s) for |` on anything before 3.10 — and the
# macOS system python3 is still 3.9. The project targets 3.10+ (see README), but the one
# module all three lanes import should not be the thing that breaks on someone's laptop.
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    """One legal move: an article link found in the current page's body."""

    index: int         # position in the numbered list shown to the LLM. 0-BASED. See PLAN.md 2.4.
    text: str          # visible anchor text shown to the LLM, e.g. "Renaissance"
    title: str         # canonical Wikipedia article title, e.g. "Renaissance"
    href: str          # ABSOLUTE href exactly as found in the HTML, e.g.
                       #   "https://en.wikipedia.org/wiki/Renaissance"
                       # Wikipedia serves Parsoid HTML: body links are absolute, NOT "/wiki/...".
    is_redirect: bool  # True if the anchor carried class="mw-redirect", i.e. this link may land
                       # on a differently-titled article. Matters for the win check.


@dataclass
class PickResult:
    candidate: Candidate | None  # None is NOT a clickable pick. Optional only so the type can
                                 # carry a degraded result; race.py must treat None as a dead end.
    reason: str        # one short sentence, shown in the reasoning log
    was_fallback: bool # True if the LLM call failed/was invalid and we fell back deterministically


@dataclass
class HopEvent:
    hop: int
    current_title: str   # CANONICAL title of the page we are standing on
    target_title: str    # canonical target. Needed to render the log line PLAN.md 1 specifies.
    t_s: float           # seconds since GO, for the projector and the post-race summary
    picked: PickResult


@dataclass
class RaceResult:
    won: bool
    winner: str                    # "bot" | "human" | "none". Only the host calling the human's
                                   # finish can set "human".
    elapsed_s: float               # wall-clock from GO to the end. THE headline number.
    hops: int | None = None
    path: list[str] | None = None  # canonical titles, start first - for the post-race replay
    reason: str | None = None      # exactly one of: "won" | "hop_limit_reached" | "bot_stuck"
                                   #   | "dead_end" | "human_finished_first" | "error"
    error: str | None = None


@dataclass
class SessionHandle:
    id: str            # stable session id. The Steel reference says to use THIS for machine
                       # parsing, not the name. Log it - you need it to stop a leaked session.
    name: str          # the --session name we chose, e.g. "speedrun-1770000000"
    live_url: str      # projector URL for Steel's live view. The probe must confirm whether the
                       # JSON key is `live_url` or `liveUrl`. Do not guess: wrong key -> None on
                       # the projector.
    session_timeout_ms: int  # echo back what Steel actually granted, so the host can see the
                             # session clock. THIS is the timeout that ends a race (see 2.3).
