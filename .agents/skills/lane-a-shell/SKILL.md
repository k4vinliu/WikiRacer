---
name: lane-a-shell
description: >-
  Implements WikiRacer Lane A (shell, flow, referee): Setup, Results, shared
  chrome, wikiApi, pairs, gameStore, useClock, mockFeed, sseFeed, App.tsx.
  Use when building those files, the race clock, title validation, difficulty,
  or the mock agent feed. Do not use for ArticleFrame, links, picker, or Steel.
---

# Lane A — Shell, Flow & Referee

You own the app chrome, the two portrait screens, the Wikipedia fetch module, the
curated pairs, the referee, and both agent feeds. You do **not** own the article
renderer or the Python agent.

**This is FRONTEND.md Lane A, not PLAN.md Package A.** Package A (`links.py`) is Lane B.

## Read first

`CLAUDE.md` → `AGENTS.md` → `FRONTEND.md` §0, §2.4, §2.6–2.7, §3, §4.1–4.2, §4.4, §5.1, §5.4–5.5, §6, §7, §9.1–9.2.

Verbatim snippets you must not paraphrase live in [reference.md](reference.md).

## Own these files — only these

```
web/src/components/Pill.tsx
web/src/components/TopNav.tsx
web/src/components/TimerBar.tsx
web/src/components/TimerDigits.tsx
web/src/components/TitleInput.tsx
web/src/components/Card.tsx
web/src/components/InlineError.tsx
web/src/components/DifficultySegment.tsx
web/src/lib/wikiApi.ts
web/src/lib/pairs.ts
web/src/state/gameStore.ts
web/src/state/useClock.ts
web/src/screens/Setup.tsx
web/src/screens/Results.tsx
web/src/App.tsx
web/src/agent/mockFeed.ts
web/src/agent/sseFeed.ts
web/src/agent/index.ts
```

Import `web/src/agent/types.ts` and `web/src/styles/theme.css`. **Do not edit them** — prologue-frozen.

If `web/` does not exist, the §9.0 prologue has not landed. Stop and say so. Do not run `npm create vite` on this branch unless the team assigned you the prologue.

## Do not create / do not touch

- `speedrun/display.py`, `tests/test_display.py`, `tests/test_wiki.py`
- `web/src/lib/links.ts`, `articleHtml.ts`, `ArticleFrame.tsx`, `article.css`, `Race.tsx`
- Any `speedrun/*.py` except by asking Lane C
- Theme token values in `theme.css`
- `rest_v1/page/html` anywhere
- `pushState` of the current article into the app URL

## Order of work (`FRONTEND.md` §9.2)

1. `Pill` — `variant: "black" | "grey" | "ghost"`, `size: "sm" | "md"`. Everything imports this.
2. `wikiApi` + `pairs` — see traps below. Copy `PAIRS` from [reference.md](reference.md).
3. **`gameStore` stub first (~20 min) and make it importable.** Lane B is blocked until `useGame()` and `playerNavigated({ title, anchorText })` exist. Then write the real reducer.
4. `useClock` + `TimerDigits` — eyeball the §3.3 jitter fix at 92px immediately.
5. **`mockFeed` before the Setup screen.** Highest-leverage file in the project.
6. `TopNav` → `TitleInput` + `DifficultySegment` → `Setup` → `App` → `Results` (all six outcomes) → `sseFeed`.

## Hard rules

1. **HTML flavor.** `action=parse&prop=text` only. `rest_v1` yields `./Title` hrefs and an empty move set.
2. **Win check is canonical title**, never URL. Player title comes from `parse.title`.
3. **Clock.** `elapsedMs = performance.now() - t0`. `rAF` repaints digits; it does not measure time. Never accumulate `setInterval` ticks.
4. **Two-phase start.** Start click → `arming` until the player's start article is painted **and** the agent feed emits `ready` (20s budget, then back to setup). Clock starts at GO, not at Start.
5. **Adjudicate on event timestamps**, not arrival order. Stamp the player at **click**, not fetch-resolve. Never reverse an announced winner. No `"tie"` — margin < 1.0s gets "Photo finish — won by 0.4s".
6. **`hop_limit_reached` / `dead_end` does not end the human's race.** Agent panel gives up; the human can still win.
7. **Mid-race reload is not supported.** Keep SSE replay-on-connect + `seq` dedupe. A reload shows "Race abandoned" and the dropped stream must `POST /stop`.
8. **Design authority is our tokens + Fraunces/Inter.** dialed.gg is a white grotesque site — do not "correct" the palette against it.
9. **Nav pill is `--surface-grey`.** `--accent-black` is the single primary CTA only.
10. **Never put a bare grey pill on the beige page.** Pill inputs sit inside a `--card-green` card.
11. **`--text-on-light-subtle` (#6E756C) is ≥18.66px only.**
12. Every `fetch` checks `res.ok`, has a timeout, and throws `WikiError(status)`. Cache by canonical title. Concurrency cap 3.

## `wikiApi.ts` traps (both already reproduced)

**(a) Normalization key.** `enc()` sends spaces as underscores, so `normalized[].from` is `"barack_obama"`. Looking up the raw spaced string misses and `Start Race` stays disabled. Use `key(t) = t.replace(/ /g, "_")` and the two-step `resolve` in [reference.md](reference.md).

**(b) No `res.ok`.** A Wikipedia 429's `text/plain` body into `res.json()` is a silent dead race. Every fetch: `if (!res.ok) throw new WikiError(res.status)`.

Nothing else may talk to wikipedia.org.

## `gameStore` — you are the referee

State machine: `setup → validating → arming → countdown → racing → finished`.

Owns: both trails, both hop counts, `t0`, the win check, the single `finished` transition.

`Race.tsx` (Lane B) consumes you **read-only** via `useGame()` and calls exactly one action: `playerNavigated({ title, anchorText })`. You wire the agent feed in `App.tsx`.

Stub shape Lane B needs on day one:

```ts
export function useGame(): GameSnapshot;
export function playerNavigated(move: { title: string; anchorText: string }): void;
```

`Winner` literals are `"bot" | "human" | "none"` — same as `RaceResult.winner`. No mapping layer.

## `mockFeed` before Setup

```ts
export function mockFeed(pair: Pair, speed = 1): AgentFeed;
export function makeFeed(pair: Pair): AgentFeed {
  return new URLSearchParams(location.search).get("agent") === "real"
    ? sseFeed("http://127.0.0.1:8848") : mockFeed(pair);
}
```

Every scripted hop must be a legal move under `FRONTEND.md` §5.3. Route via a known intermediate from §5.4 (e.g. Cat → Ancient Egypt → Napoleon). Verify against a real fetch once.

`anchor_text` is required on every `pick` event.

## Screens

**Setup.** Portrait hero card, content **left-aligned** (the card is centered, the text is not). Lowercase Fraunces title. Controls pinned to the card bottom under `Where to where?`: `DifficultySegment` (default Medium), two `TitleInput`s prefilled from the tier pair, ghost `Randomize`, one black `Start Race` — disabled until both titles resolve to real, **distinct** articles. Label Easy: `Easy — the agent doesn't look ahead`.

**Results.** Same hero. `--size-result` MM:SS. Stats row. Two plain `<ol>` paths. Black `Race again`, ghost `New articles`. Six outcomes — see [reference.md](reference.md).

**TopNav.** Wordmark left (Inter 500), one **grey** pill right. No theme/sound icons.

**TimerDigits.** One `<span>` per character, widths `0.64em` / `0.28em`. Copy the component from [reference.md](reference.md). `font-variant-numeric: tabular-nums` is a no-op on Fraunces.

## Difficulty (`FRONTEND.md` §5.5)

Two honest levers: the pair, and the agent settings. **No per-hop delay.**

| Tier | Pair | Agent |
|---|---|---|
| Easy | 2 hops, fanout ≥320 | Haiku, `find_target` **off** |
| Medium (default) | 2 hops narrow or ≥3 | Haiku, `find_target` on |
| Hard | ≥3 hops, fanout ≤260 | Sonnet **or** Haiku if thinking config isn't fixed |

Picking a tier fills both inputs from a random pair. Host may still type; typed pairs run at the selected tier's agent settings, and the UI says so.

## CP1 hard gate (you)

Lane B cannot start Race until you push:

- `useGame()` + `playerNavigated`
- `wikiApi.fetchArticle` returning `{ title, html }` from `action=parse`

Setup should render. Timer digits eyeballed at 92px.

## Verify

Browser, not a screenshot: Setup validate / disable / Randomize / difficulty prefills; arming; Results for each of the six endings; `?agent=real` vs default mock; reload mid-race → abandoned, no leaked assumption that the race continues. R1 in `FRONTEND.md` §10 is yours: `npm run dev` with **no API keys** must play Setup → Race → Results on `mockFeed`.
