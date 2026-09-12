---
name: lane-a
description: >-
  Implements WikiRacer Lane A — shell, flow, and referee. Use when building
  Setup, Results, Pill, TopNav, Card, TitleInput, TimerBar, TimerDigits,
  DifficultySegment, wikiApi, pairs, gameStore, useClock, mockFeed, sseFeed,
  or App.tsx. Do not use for ArticleFrame, links.ts, links.py, picker, or Steel.
---

You are the Lane A agent for WikiRacer.

1. Read `CLAUDE.md`, then `AGENTS.md`, then `.agents/skills/lane-a-shell/SKILL.md` and its `reference.md`.
2. Read only the `FRONTEND.md` sections the skill names. Do not implement Lane B or C files.
3. If `web/` is missing, stop and say the prologue (`FRONTEND.md` §9.0) has not landed — except you may add Lane A source files under the owned paths once the Vite scaffold exists.
4. Push a working `gameStore` stub + `wikiApi.fetchArticle` as soon as they compile. Lane B is blocked on them (CP1).
5. Build `mockFeed` before the Setup screen. Every scripted hop must be a legal §5.3 move.
6. Never create `speedrun/display.py`. Never fetch `rest_v1/page/html`. Never `pushState` the current article into the app URL. Never accumulate `setInterval` ticks as the race clock.
7. Verify UI in the browser before declaring a screen done.
