"""Shared test doubles for the race loop and the server: no Steel, no LLM, no network.

FakeWiki is a tiny model of Wikipedia: a link graph plus redirects. Its rules stand in for
Lane B's speedrun/links.py + speedrun/wiki.py so the loop and the server can be tested on
their own. A page's "HTML" here is just "PAGE:<canonical title>".
"""

from __future__ import annotations

import time

from speedrun import race, steel_client
from speedrun.types import Candidate, PickResult

WIKI = "https://en.wikipedia.org/wiki/"


class NoCandidates(Exception):
    pass


class FakeWiki:
    def __init__(self, links: dict[str, list], redirects: dict[str, str] | None = None):
        self.links, self.redirects = links, redirects or {}

    def canonical(self, title: str) -> str:
        return self.redirects.get(title, title)

    def extract_candidates(self, html: str, max_candidates: int = 1000) -> list[Candidate]:
        out = []
        for i, link in enumerate(self.links.get(html.removeprefix("PAGE:"), [])):
            text, title = (link, link) if isinstance(link, str) else link
            out.append(Candidate(index=i, text=text, title=title, href=WIKI + title.replace(" ", "_"),
                                 is_redirect=title in self.redirects))
        return out

    def rules(self) -> race.GameRules:
        return race.GameRules(
            extract_candidates=self.extract_candidates,
            find_target=lambda cands, target: next((c for c in cands if c.title.casefold() == target.casefold()), None),
            canonical_title=lambda html: html.removeprefix("PAGE:"),
            titles_match=lambda a, b: a.casefold() == b.casefold(),
            url_from_title=lambda t: WIKI + t.replace(" ", "_"),
            title_from_url=lambda s: s.rsplit("/wiki/", 1)[-1].replace("_", " "),
        )

    def resolve_titles(self, titles: list[str]) -> dict[str, str | None]:
        return {t: (self.canonical(t) if self.canonical(t) in self.links else None) for t in titles}


class FakeSource:
    session_id = "fake-session"
    live_url = "https://api.steel.dev/v1/sessions/fake-session/player?interactive=false&hideOverlay=true"

    def __init__(self, wiki: FakeWiki | None, fail_calls: set[int] = frozenset(), stamp: float | None = None):
        self.wiki, self.fail_calls, self.stamp = wiki, set(fail_calls), stamp
        self.opened = self.closed = False
        self.calls = 0
        self.visits: list[str] = []

    def open(self):
        self.opened = True

    def goto(self, url: str):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise steel_client.SteelTimeout("steel hung")
        title = url.rsplit("/wiki/", 1)[-1].replace("_", " ")
        self.visits.append(title)
        return "PAGE:" + self.wiki.canonical(title), (self.stamp if self.stamp is not None else time.monotonic())

    def close(self):
        self.closed = True


def scripted(*titles: str):
    """A picker that picks the candidate with each given title in turn, recording what it saw."""
    calls: list[dict] = []

    def choose(client, model, current_title, target_title, visited, candidates, hop, max_hops, banned_titles=None):
        calls.append({"current": current_title, "visited": list(visited),
                      "candidates": list(candidates), "hop": hop})
        want = titles[len(calls) - 1]
        pick = next(c for c in candidates if c.title == want)
        return PickResult(candidate=pick, reason=f"heading for {want}", was_fallback=False)

    return race.PickerFns(choose=choose, no_candidates=NoCandidates), calls
