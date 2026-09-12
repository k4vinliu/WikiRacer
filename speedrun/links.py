"""THE GAME RULE, in Python. Lane B. PLAN.md §4.A.

`web/src/lib/links.ts` is the other half of this file and the two MUST agree.
If the player and the agent have different move sets, one of them gets robbed of
a win. Any change here is a change there, in the same commit.

What this parses: the READ VIEW HTML that `steel browser content` returns, in
which article-body hrefs are ABSOLUTE (`https://en.wikipedia.org/wiki/Foo`) and
the content is wrapped in `#mw-content-text`. Verified on 2026-09-12: 1,052
absolute vs 66 relative hrefs on `Python (programming language)`, and all 66 of
the relative ones are site chrome outside `#mw-content-text`. The frontend
fetches a different flavour (`action=parse`, which emits `/wiki/Foo`), so the
href pattern below accepts both. It must never accept `./Foo` — that is
`rest_v1` output and resolving it against our own origin is not an article.

Offline. No network, no credentials.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from speedrun.types import Candidate

# --------------------------------------------------------------------------- #
# The exclusion list. Keep in lockstep with EXCLUDE in web/src/lib/links.ts.
# --------------------------------------------------------------------------- #
EXCLUDE_SELECTOR = ", ".join(
    [
        # navigation chrome
        ".navbox", ".navbox-styles", ".vertical-navbox", ".sidebar", ".side-box",
        ".sistersitebox", ".metadata", ".portalbox", ".navbar", ".catlinks",
        # collapsed / non-rendering
        ".mw-collapsed", ".noprint", "[hidden]",
        # citations
        ".reference", ".reflist", ".mw-references-wrap", "ol.references",
        # editorial affordances
        ".mw-editsection", ".mw-jump-link",
    ]
)

# DELIBERATELY NOT EXCLUDED, both checked, both legal moves:
#   .infobox  — 69 legitimate links on the Python article
#   .hatnote  — body content, often literal inline "See also:" lines, i.e.
#               exactly the lateral move that wins wiki races

NAMESPACES = frozenset(
    {
        "File", "Image", "Media", "Category", "Special", "Help", "Portal",
        "Template", "Module", "Draft", "User", "Wikipedia", "Project",
        "MediaWiki", "TimedText", "Book", "Talk",
        "File talk", "Category talk", "Help talk", "Portal talk",
        "Template talk", "Module talk", "Draft talk", "User talk",
        "Wikipedia talk", "Project talk", "MediaWiki talk", "TimedText talk",
        "Book talk",
    }
)

# Absolute OR root-relative. NOT `./Title`.
ARTICLE_HREF = re.compile(
    r"^(?:https?://en\.wikipedia\.org)?/wiki/([^?#]+)(?:#.*)?$"
)
_EXTERNAL = re.compile(r"^https?://", re.I)
_OUR_HOST = re.compile(r"^https?://en\.wikipedia\.org/", re.I)


def _ucfirst(s: str) -> str:
    """Wikipedia titles are case-sensitive except for the first character."""
    return s[0].upper() + s[1:] if s else s


def normalize_title(raw: str) -> str:
    return _ucfirst(unquote(str(raw)).replace("_", " ").strip())


def title_from_href(href: str | None) -> str | None:
    """The article title an href points at, or None if it isn't a legal move."""
    if not href:
        return None
    href = href.strip()
    m = ARTICLE_HREF.match(href)
    if not m:
        return None
    # A cross-host href can still contain /wiki/ — real bodies link to things
    # like code.google.com/p/x/wiki/Y.
    if _EXTERNAL.match(href) and not _OUR_HOST.match(href):
        return None
    if "#cite_note" in href or "#cite_ref" in href:
        return None

    title = normalize_title(m.group(1))
    if not title:
        return None
    head, sep, _ = title.partition(":")
    if sep and head in NAMESPACES:
        return None
    return title


def extract_candidates(
    html: str,
    max_candidates: int = 1000,
    self_title: str | None = None,
) -> list[Candidate]:
    """The legal move set for one article, in document order.

    `index` is 0-based and contiguous over the RETURNED list. It is what gets
    rendered to the LLM and what we dereference, and those must be the same
    number — see PLAN.md §4.C, the only silent-wrong-answer bug in the plan.
    """
    soup = BeautifulSoup(html, "html.parser")

    scope = soup.select_one("#mw-content-text") or soup.select_one(
        ".mw-parser-output"
    )
    root = scope if scope is not None else soup

    for node in root.select(EXCLUDE_SELECTOR):
        node.decompose()

    self_norm = normalize_title(self_title) if self_title else None
    seen: set[str] = set()
    out: list[Candidate] = []

    for a in root.find_all("a", href=True):
        if len(out) >= max_candidates:
            break

        title = title_from_href(a.get("href"))
        if title is None or title in seen or title == self_norm:
            continue

        classes = a.get("class") or []
        if "new" in classes:  # red link: the article does not exist
            continue

        seen.add(title)
        text = a.get_text(strip=True) or title
        out.append(
            Candidate(
                index=len(out),
                text=text,
                title=title,
                href=a["href"],
                is_redirect="mw-redirect" in classes,
            )
        )
    return out


def find_target(
    candidates: list[Candidate], target_title: str
) -> Candidate | None:
    """Is the target link on this page? Then it is a guaranteed win.

    `race.py` calls this before every picker call: no LLM call, no chance of an
    LLM error at the winning move, one less hop of latency. Must run BEFORE any
    truncation — real directly-linked targets sit past index 900 on long
    articles. PLAN.md §4.A.
    """
    want = normalize_title(target_title)
    for c in candidates:
        if c.title == want:
            return c
    return None


if __name__ == "__main__":  # throwaway: eyeball a candidate list in 5 seconds
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        sys.exit("usage: python -m speedrun.links <file.html> [target]")
    cands = extract_candidates(open(path, encoding="utf-8").read())
    print(f"{len(cands)} legal moves")
    for c in cands[:40]:
        flag = " (redirect)" if c.is_redirect else ""
        print(f"  {c.index:>4}. {c.text} -> {c.title}{flag}")
    if len(sys.argv) > 2:
        print("find_target:", find_target(cands, sys.argv[2]))
