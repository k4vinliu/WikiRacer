"""Lane C's debugging view: one stderr line per agent event.

This replaces display.py, which is deleted (FRONTEND.md §8). The projector shows the React
AgentLog; this is for whoever is watching the terminal. It is plain ASCII on purpose, so no
terminal encoding can turn a log line into an exception.
"""

from __future__ import annotations

import sys
from typing import TextIO


def format_event(e: dict, prefix: str = "") -> str:
    t = e.get("t")
    if t == "ready":
        body = f"READY     session {e['session_id']} | live view {e['live_url'] or '(none: no browser)'}"
    elif t == "thinking":
        body = f"THINKING  {e['article']} | {e['n_candidates']} legal links"
    elif t == "pick":
        # The anchor text as it appeared on the page is the evidence the link existed
        # (PLAN.md §4.D). The canonical title beside it shows where a redirect went.
        shown = f'"{e["anchor_text"]}"'
        if e["anchor_text"].casefold() != e["to"].casefold():
            shown += f" ({e['to']})"
        flag = "  [FALLBACK]" if e.get("was_fallback") else ""
        body = f"PICK      {e['from']} -> {shown}  {e['reason']}{flag}"
    elif t == "arrive":
        body = f"ARRIVE    hop {e['hop']} | {e['article']}"
    elif t == "done":
        detail = f": {e['message']}" if e.get("message") else ""
        body = f"DONE      {e['reason']} after {e['hops']} hop(s){detail}"
    elif t == "error":
        body = f"ERROR     {'(fatal) ' if e.get('fatal') else ''}{e['message']}"
    else:
        body = f"?         {e!r}"
    return f"{prefix}[{e.get('at', 0) / 1000:7.2f}s] {body}".replace("\n", " ")


def print_event(e: dict, stream: TextIO | None = None, prefix: str = "") -> None:
    print(format_event(e, prefix), file=stream or sys.stderr, flush=True)
