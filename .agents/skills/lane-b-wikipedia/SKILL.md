---
name: lane-b-wikipedia
description: >-
  Implements WikiRacer Lane B — article renderer, shared link extractor, and
  Claude picker. Use when building links.ts, ArticleFrame, article.css, Race,
  PlayerPanel, AgentPanel, AgentLog, PathTrail, TargetBadge, speedrun/links.py,
  wiki.py, picker.py, or test_links.py.
---

# Lane B — Wikipedia, Renderer & Picker

One legal-move rule, two languages. You also own the Race screen and the Claude picker
(`PLAN.md` §4.C moved here). You do **not** own Setup, Results, `gameStore`, or Steel.

**PLAN.md §4.A is yours. FRONTEND.md Lane A is not.**

## Read first

`CLAUDE.md` → `AGENTS.md` → `FRONTEND.md` §2.1–2.2, §4.3, §5, §6.1, §9.1–9.2 → `PLAN.md` §4.A and §4.C (and §2.4 for the tool contract).

## Own these files — only these

```
web/src/lib/links.ts
web/src/lib/articleHtml.ts
web/src/components/ArticleFrame.tsx
web/src/styles/article.css
web/src/components/PlayerPanel.tsx
web/src/components/AgentPanel.tsx
web/src/components/AgentLog.tsx
web/src/components/PathTrail.tsx
web/src/components/TargetBadge.tsx
web/src/screens/Race.tsx
speedrun/links.py
speedrun/wiki.py
speedrun/picker.py
tests/test_links.py
tests/test_picker.py
```

Import `useGame()` and `<TimerBar>` from Lane A. **Do not edit them.** If they are missing, ask — do not invent a second store.

## Do not create

`speedrun/display.py`, `tests/test_display.py`, `tests/test_wiki.py` (fold wiki asserts into `test_links.py`).

## Order of work

1. `links.ts` first.
2. `articleHtml.ts` → `ArticleFrame` (srcdoc iframe, CSS inlined once, delegated click).
3. `article.css` — **time-box 1.5h hard**: hide list only, then type scale, then `table/.infobox { display:block; overflow-x:auto }` and `img { max-width:100% }`.
4. `PathTrail` / `TargetBadge` / `AgentLog` → `PlayerPanel` / `AgentPanel` → `Race.tsx`.
5. `links.py` + `test_links.py` — fixture test **red first**, then green.
6. `wiki.py` helpers used by the fixture/win check.
7. `picker.py` last. Read the `link_index` warning before you render the list.

## Extraction rule — must match in both languages

Legal moves = in-body article links, excluding:

```
.navbox, .sidebar, .side-box, .sistersitebox, .metadata, .portalbox, .navbar,
.mw-collapsed, .noprint, [hidden],
.reference, ol.references, .reflist, .mw-references-wrap, .mw-editsection
```

plus namespaces `File: Category: Special: Help: Portal: Template: Module: Draft: User: Wikipedia: MediaWiki: TimedText: Book: Talk:` and `_talk:` variants, plus `#cite_note` / `#cite_ref`, plus self-links.

**Keep `.infobox`. Keep `.hatnote`.** A grep for `hatnote` in `web/src/styles/` is a fail.

Asymmetries that must be fixed on **both** sides or one racer gets extra moves:

- TS must include `.reference, ol.references, .reflist, .mw-references-wrap`
- `links.py` must include `.noprint`

Href regex (absolute **or** relative; reject any other host):

```
^(?:https?://en\.wikipedia\.org)?/wiki/(?P<title>[^?#]+)$
```

HTML source is `action=parse&prop=text` (`/wiki/…` hrefs). **Never `rest_v1/page/html`** (`./Title` → 0 candidates). Read-view HTML (the Python fixture) is absolute `https://en.wikipedia.org/wiki/…` — the regex accepts both.

Python: `BeautifulSoup(html, "html.parser")` — not `lxml`. Scope `#mw-content-text`. Dedupe by title, first wins. `index` is **0-based** in final order. `max_candidates=1000`. `find_target` runs **before** truncation.

`Candidate.text` is `a.get_text(strip=True)`, fallback `Candidate.title` — not the `title=` attribute.

## `ArticleFrame` gate

`candidates.has(title)` is not optional. CSS hide is not enough — measured illegal-but-visible links: Python 157, Roman Empire 68. `preventDefault` on every click; only legal titles call `onMove({ title, anchorText })`.

Same-origin `srcdoc` iframe. Inline article CSS once (a `<link>` flashes unstyled on hop 1). Shadow DOM breaks TemplateStyles — do not use it.

Never `pushState` the article into the app URL.

## Picker (`PLAN.md` §4.C) — the silent bug

Render `f"{c.index}. {c.text} -> {c.title}"`. **Never `enumerate(candidates, 1)`.** A 1-based list with 0-based validation clicks the *next* link every hop, always in range, every test green.

`link_index` is 0-based. Empty candidates → `NoCandidatesError`, no API call. `AuthenticationError` re-raises. Filter `visited` and `banned_titles` before numbering.

Default model `claude-haiku-4-5`. Sonnet 5 needs `thinking={"type":"disabled"}` or it 100%-fallbacks.

## Fixture acceptance

```
python3.11 -m pytest tests/test_links.py
```

`len(extract_candidates(fixture)) > 200`, `"Guido van Rossum"` present, no blocked namespace titles, `find_target(..., "Guido van Rossum")` is not None. Write unit-fixture hrefs **absolute**.
