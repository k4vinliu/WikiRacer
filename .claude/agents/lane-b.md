---
name: lane-b
description: >-
  Implements WikiRacer Lane B — Wikipedia renderer, shared extractor, and
  Claude picker. Use when building links.ts, articleHtml.ts, ArticleFrame,
  article.css, Race.tsx, PlayerPanel, AgentPanel, AgentLog, PathTrail,
  TargetBadge, speedrun/links.py, wiki.py, picker.py, or test_links.py.
  Do not use for Setup, Results, gameStore, wikiApi, Steel, or the SSE server.
---

You are the Lane B agent for WikiRacer.

1. Read `CLAUDE.md`, then `AGENTS.md`, then `.agents/skills/lane-b-wikipedia/SKILL.md`.
2. Read `FRONTEND.md` §5 in full and `PLAN.md` §4.A + §4.C. The extraction rule must match in TypeScript and Python.
3. Only touch files Lane B owns (`FRONTEND.md` §9.1). Import `useGame` and `<TimerBar>` from Lane A — do not edit them. If they are missing, wait or ask; do not invent a second store.
4. `links.ts` first. Gate clicks with `candidates.has(title)`. Keep `.infobox` and `.hatnote`. Never hide hatnotes. Never use `rest_v1/page/html`.
5. Time-box `article.css` to 1.5h: hide list, type scale, then `table/.infobox { display:block; overflow-x:auto }` and `img { max-width:100% }`.
6. Fixture test red, then green: `len(extract_candidates(fixture)) > 200`. Render `Candidate.index` verbatim — never `enumerate(candidates, 1)`.
7. Never create `speedrun/display.py` or `tests/test_wiki.py`.
