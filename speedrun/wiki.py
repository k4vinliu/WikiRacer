"""Title normalization and the win-check primitive. Lane B. PLAN.md §4.A / §2.2.

The one thing to understand before editing this file: **never derive the
article title from the URL.** MediaWiki serves redirects *in place* — verified
2026-09-12, `GET /wiki/Obama` returns HTTP 200 with **zero** redirects, the URL
still reads `/wiki/Obama`, and the page is *Barack Obama* with
`<link rel="canonical" href=".../Barack_Obama">`. Same for `/wiki/Snakes` and
`/wiki/WWII`. Roughly 14-18% of article body links are redirects.

So a URL comparison both misses wins the bot has already achieved and makes any
race unwinnable whose target the host typed as a redirect. `title_from_url` is a
normalization helper for input the host typed; `canonical_title_from_html` is
what the win check runs on.

Offline. No network, no credentials.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote

from bs4 import BeautifulSoup

_WIKI = "https://en.wikipedia.org/wiki/"
_SPLIT_WIKI = re.compile(r"/wiki/", re.I)


def _ucfirst(s: str) -> str:
    """Wikipedia titles are case-sensitive except for the first character."""
    return s[0].upper() + s[1:] if s else s


def normalize_title(raw: str) -> str:
    return _ucfirst(unquote(str(raw)).replace("_", " ").strip())


def canonical_title_from_html(html: str) -> str:
    """THE WIN-CHECK PRIMITIVE. The page's real title, per Wikipedia itself.

    Reads `<link rel="canonical">`, falling back to `<h1 id="firstHeading">`.
    Both come out of the HTML we already fetched, so this costs zero extra
    round trips.

    Note the frontend does NOT use this: `action=parse` returns `parse.title`
    already redirect-resolved in the same request. A JS port of this function
    would return None against that output, because `rel="canonical"` does not
    appear in a parse fragment (verified: count 0 there, present on the read
    view). Two sources, one authority — Wikipedia's own.
    """
    soup = BeautifulSoup(html, "html.parser")

    link = soup.find("link", rel=lambda v: v and "canonical" in v)
    href = link.get("href") if link else None
    if href:
        parts = _SPLIT_WIKI.split(href, maxsplit=1)
        if len(parts) == 2 and parts[1]:
            return normalize_title(parts[1].split("#")[0])

    heading = soup.find(id="firstHeading")
    if heading is not None:
        text = heading.get_text(strip=True)
        if text:
            return normalize_title(text)

    raise ValueError(
        "no <link rel=canonical> and no #firstHeading in this HTML — cannot "
        "determine the canonical title, and guessing from the URL is the bug "
        "this function exists to prevent"
    )


def title_from_url(url_or_title: str) -> str:
    """Normalize whatever the host typed. NOT for win checks."""
    s = str(url_or_title).strip()
    parts = _SPLIT_WIKI.split(s, maxsplit=1)
    raw = parts[1] if len(parts) == 2 else s
    return normalize_title(raw.split("#")[0])


def url_from_title(title: str) -> str:
    """`"Snake"` -> `"https://en.wikipedia.org/wiki/Snake"`.

    The CLI and the acceptance commands both pass bare titles, and nothing in
    v1 of the plan owned this conversion.
    """
    t = normalize_title(title).replace(" ", "_")
    return _WIKI + quote(t, safe="_(),!$-'*.~:/")


def titles_match(a: str, b: str) -> bool:
    """The only title comparison on the Python side. Both racers' wins use it."""
    return normalize_title(a).casefold() == normalize_title(b).casefold()
