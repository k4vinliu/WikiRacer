"""Tests for speedrun/links.py and speedrun/wiki.py. Lane B.

The FIRST test in this file is the one that matters. PLAN.md §4.A:

    "This one test is what moves this package's worst failure mode from
     'discovered on stage' to 'discovered before lunch'."

v1 of the plan kept only hrefs starting with `/wiki/` and mandated hand-written
inline fixtures — which would have been written with the same wrong assumption,
so the whole suite would have gone green while the function returned [] against
every real article. Hence `tests/fixtures/python_programming_language.html`: a
real 1 MB page, committed, asserted against. Everything stays offline.

Run: python3.11 -m pytest tests/test_links.py -q
"""

from pathlib import Path

import pytest

from speedrun.links import extract_candidates, find_target
from speedrun.wiki import (
    canonical_title_from_html,
    title_from_url,
    titles_match,
    url_from_title,
)

FIXTURE = Path(__file__).parent / "fixtures" / "python_programming_language.html"

BLOCKED_PREFIXES = (
    "File:", "Image:", "Media:", "Category:", "Special:", "Help:", "Portal:",
    "Template:", "Module:", "Draft:", "User:", "Wikipedia:", "MediaWiki:",
    "TimedText:", "Book:", "Talk:",
)


@pytest.fixture(scope="module")
def real_html() -> str:
    assert FIXTURE.exists(), f"missing committed fixture: {FIXTURE}"
    return FIXTURE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The fixture test. Red before green.
# --------------------------------------------------------------------------- #

def test_real_article_yields_many_candidates(real_html):
    """The v1-killer. Wikipedia serves ABSOLUTE hrefs in article bodies."""
    cands = extract_candidates(real_html)
    assert len(cands) > 200, (
        f"got {len(cands)} candidates from a real 1 MB article. If this is 0, the "
        "href filter is rejecting absolute hrefs — see PLAN.md §4.A and "
        "FRONTEND.md §2.2."
    )


def test_real_article_contains_a_known_body_link(real_html):
    titles = {c.title for c in extract_candidates(real_html)}
    assert "Guido van Rossum" in titles


def test_real_article_excludes_all_blocked_namespaces(real_html):
    offenders = [
        c.title
        for c in extract_candidates(real_html)
        if c.title.startswith(BLOCKED_PREFIXES)
    ]
    assert not offenders, f"namespace links leaked into the move set: {offenders[:8]}"


def test_real_article_indices_are_zero_based_and_contiguous(real_html):
    """PLAN.md §4.C: the only silent-wrong-answer bug in the plan. If the index
    the LLM is shown is not the index we dereference, the agent clicks the link
    AFTER the one it reasoned about, on every hop, always in range."""
    cands = extract_candidates(real_html)
    assert [c.index for c in cands] == list(range(len(cands)))


def test_find_target_locates_a_directly_linked_article(real_html):
    cands = extract_candidates(real_html)
    hit = find_target(cands, "Guido van Rossum")
    assert hit is not None and hit.title == "Guido van Rossum"


def test_find_target_returns_none_when_absent(real_html):
    assert find_target(extract_candidates(real_html), "Kangaroo") is None


def test_real_article_strips_navigation_chrome(real_html):
    """On this exact page, 151 of v1's 300 candidates sat inside ONE `.sidebar`
    block — and MediaWiki's collapsing is JS-driven, so with no JS it renders
    fully expanded. FRONTEND.md §5.3."""
    titles = {c.title for c in extract_candidates(real_html)}
    # A sidebar/navbox-only title from this page's programming-language template.
    assert "Comparison of programming languages" not in titles


# --------------------------------------------------------------------------- #
# Inline fixtures. NOTE: hrefs are written ABSOLUTE, the form Wikipedia really
# serves. An inline fixture using "/wiki/Foo" agrees with a bug instead of
# catching it — that is precisely how v1's blocker survived review.
# --------------------------------------------------------------------------- #

def _page(body: str) -> str:
    return f'<html><body><div id="mw-content-text">{body}</div></body></html>'


W = "https://en.wikipedia.org/wiki"


def test_accepts_absolute_and_relative_rejects_cross_host():
    html = _page(f"""
      <p>
        <a href="{W}/Renaissance">Renaissance</a>
        <a href="/wiki/Florence">Florence</a>
        <a href="https://code.google.com/p/x/wiki/Y">not wikipedia</a>
        <a href="https://en.wikipedia.org/wiki/Renaissance">dupe</a>
      </p>
    """)
    titles = [c.title for c in extract_candidates(html)]
    assert titles == ["Renaissance", "Florence"]


def test_rejects_namespaces_but_keeps_colons_in_real_titles():
    html = _page(f"""
      <p>
        <a href="{W}/File:X.jpg">file</a>
        <a href="{W}/Category:Y">cat</a>
        <a href="{W}/Special:Random">random</a>
        <a href="{W}/Batman:_The_Animated_Series">Batman</a>
      </p>
    """)
    assert [c.title for c in extract_candidates(html)] == [
        "Batman: The Animated Series"
    ]


def test_strips_references_sidebars_and_navboxes():
    html = _page(f"""
      <p><a href="{W}/Legal_one">one</a></p>
      <sup class="reference"><a href="{W}/Citation_link">[1]</a></sup>
      <div class="reflist"><a href="{W}/Reflist_link">ref</a></div>
      <div class="sidebar"><a href="{W}/Sidebar_link">side</a></div>
      <div class="navbox"><a href="{W}/Navbox_link">nav</a></div>
      <div class="mw-collapsed"><a href="{W}/Collapsed_link">collapsed</a></div>
      <div class="noprint"><a href="{W}/Noprint_link">noprint</a></div>
      <p><a href="{W}/Legal_two">two</a></p>
    """)
    assert [c.title for c in extract_candidates(html)] == ["Legal one", "Legal two"]


def test_keeps_infobox_and_hatnote_links():
    """Both are legal moves and were checked. See FRONTEND.md §5.3."""
    html = _page(f"""
      <div class="hatnote"><a href="{W}/Hatnote_target">See also</a></div>
      <table class="infobox"><tr><td><a href="{W}/Infobox_target">box</a></td></tr></table>
    """)
    titles = {c.title for c in extract_candidates(html)}
    assert titles == {"Hatnote target", "Infobox target"}


def test_skips_cite_anchors_and_self_links():
    html = _page(f"""
      <a href="{W}/Snake#cite_note-1">cite</a>
      <a href="{W}/Snake">self</a>
      <a href="{W}/Python_(genus)">other</a>
    """)
    titles = [c.title for c in extract_candidates(html, self_title="Snake")]
    assert titles == ["Python (genus)"]


def test_marks_redirects():
    html = _page(f'<a class="mw-redirect" href="{W}/Serpentes">Serpentes</a>')
    (c,) = list(extract_candidates(html))
    assert c.is_redirect is True


def test_skips_red_links():
    html = _page(f'<a class="new" href="{W}/Nonexistent_article">red</a>')
    assert list(extract_candidates(html)) == []


def test_anchor_text_falls_back_to_title_when_empty():
    html = _page(f'<a href="{W}/Renaissance"><img src="x.png"></a>')
    (c,) = list(extract_candidates(html))
    assert c.text == "Renaissance"


def test_truncates_and_reindexes():
    links = "".join(f'<a href="{W}/Article_{i}">a{i}</a>' for i in range(50))
    cands = extract_candidates(_page(links), max_candidates=10)
    assert len(cands) == 10
    assert [c.index for c in cands] == list(range(10))
    assert cands[0].title == "Article 0"  # document order preserved


def test_falls_back_to_whole_doc_when_scope_selector_missing():
    html = f'<html><body><p><a href="{W}/Renaissance">R</a></p></body></html>'
    assert [c.title for c in extract_candidates(html)] == ["Renaissance"]


def test_rejects_rest_v1_relative_hrefs():
    """`rest_v1/page/html` emits `./Title`. Accepting it would resolve against
    OUR origin, which is not a Wikipedia article. FRONTEND.md §2.2."""
    assert list(extract_candidates(_page('<a href="./Renaissance">R</a>'))) == []


# --------------------------------------------------------------------------- #
# wiki.py
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Snake", "Snake"),
        ("  Snake  ", "Snake"),
        (f"{W}/Python_(programming_language)", "Python (programming language)"),
        ("/wiki/Guido_van_Rossum", "Guido van Rossum"),
        (f"{W}/Snake#Venom", "Snake"),
        (f"{W}/Monty_Python%27s_Flying_Circus", "Monty Python's Flying Circus"),
        (f"{W}/AT%26T", "AT&T"),
        (f"{W}/Caf%C3%A9", "Café"),
    ],
)
def test_title_from_url(raw, expected):
    assert title_from_url(raw) == expected


def test_url_from_title_round_trips():
    for t in ["Snake", "Python (programming language)", "AT&T", "Café",
              "Monty Python's Flying Circus"]:
        assert title_from_url(url_from_title(t)) == t


def test_canonical_title_beats_the_url():
    """MediaWiki serves redirects IN PLACE: /wiki/Obama is HTTP 200 with the URL
    unchanged and the content of Barack Obama. Deriving the title from the URL
    is how the bot stands on the target and does not win. PLAN.md §1."""
    html = (
        '<html><head><link rel="canonical" '
        'href="https://en.wikipedia.org/wiki/Barack_Obama"></head>'
        '<body><h1 id="firstHeading">Barack Obama</h1></body></html>'
    )
    assert canonical_title_from_html(html) == "Barack Obama"


def test_canonical_falls_back_to_first_heading():
    html = '<html><body><h1 id="firstHeading">Snake</h1></body></html>'
    assert canonical_title_from_html(html) == "Snake"


def test_canonical_on_the_real_fixture(real_html):
    assert canonical_title_from_html(real_html) == "Python (programming language)"


@pytest.mark.parametrize(
    "a,b,same",
    [
        ("Snake", "snake", True),
        ("Guido van Rossum", "Guido_van_Rossum", True),
        ("  Snake ", "Snake", True),
        ("Snake", "Snakes", False),
        ("Python (genus)", "Python (programming language)", False),
    ],
)
def test_titles_match(a, b, same):
    assert titles_match(a, b) is same
