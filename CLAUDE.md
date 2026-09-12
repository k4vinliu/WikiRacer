# WikiRacer — read this before you touch anything

A hackathon project: **a human races an AI agent on Wikipedia**, in a web app we build.
The agent browses with the Steel CLI and picks links with Claude. The human races in the
left panel of the same app. One shared clock. First to the target article wins.

## Read order — do not skip this

| If your task is… | Read, in this order |
|---|---|
| **anything user-facing** (React, CSS, screens, the renderer, the game feel) | **`FRONTEND.md`** → then `PLAN.md` §2 for the shared types |
| **the agent** (Steel, the LLM link picker, the race loop, the server) | `PLAN.md` §1–§2, then your §4.x package → then `FRONTEND.md` §6 for the event schema |
| **link extraction / titles** (either language) | `PLAN.md` §4.A **and** `FRONTEND.md` §5 — the rule must match in both |
| **who builds what** | `ASSIGNMENTS.md` |

**`PLAN.md` is SUPERSEDED for everything user-facing.** It describes a terminal UI
(`rich`) and says the human races on their own laptop, out of code scope. Both are dead.
`FRONTEND.md` wins on anything visual, interactive, or about the human player.
`PLAN.md` §2 still wins on the Python contracts.

**`speedrun/display.py` does not exist and must not be created.** If a document tells you
to build it, that document is out of date.

## Hard-won rules that are expensive to rediscover

Every one of these was verified against the live service, and most of them were a bug first.

1. **Article HTML comes from `action=parse&prop=text`. Never `rest_v1/page/html`.**
   The three flavors disagree on href form — read view emits absolute `https://en.wikipedia.org/wiki/…`,
   `action=parse` emits `/wiki/…`, `rest_v1` emits `./Title`. Our extraction regex yields
   **485 / 485 / 0** candidates respectively. `rest_v1` silently returns an empty move set.
2. **Win detection compares the CANONICAL TITLE, never the URL.** MediaWiki serves
   redirects in place: `GET /wiki/Obama` is HTTP 200 with the URL still `/wiki/Obama` and
   the content of *Barack Obama*. ~14–18% of body links are redirects. Frontend gets the
   canonical from `parse.title`; Python gets it from `<link rel="canonical">`.
3. **`link_index` in the Claude tool call is 0-BASED.** Render the candidate list from
   `Candidate.index` verbatim. Never `enumerate(candidates, 1)`. Getting this wrong makes
   the agent click the link *after* the one it reasoned about, on every hop, always in
   range, so nothing errors and every test passes. See `PLAN.md` §4.C.
4. **`steel browser start` needs BOTH `--session-timeout 900000` and
   `--inactivity-timeout 0`.** They are independent. `timeout` defaults to 5 minutes, is
   create-time only, and is what actually kills a live race.
5. **The agent MOVES by navigating to the chosen href.** It does not resolve an element ref
   and click. The extractor enforces legality, so the reasoning log must name the anchor
   text as it appeared on the page.
6. **Use `python3.11`, not `python3`** (system Python here is 3.9.6, and `X | None` in a
   dataclass annotation raises `TypeError` on it).
7. **Never `pushState` the current article into the app URL.** It hands the player an
   editable address bar and defeats the whole renderer.
8. **Every `fetch` and every `subprocess.run` needs error handling and a timeout.** A
   Wikipedia 429 whose body flows unchecked into a parser produces an empty move set and a
   race that silently cannot be won. This has already happened twice on this project.

## Design authority

The visual spec's twelve hex tokens and Fraunces/Inter **are** the design authority
(`FRONTEND.md` §3). The project was inspired by dialed.gg, but **dialed.gg is a white-page,
near-black-card, all-grotesque site with none of our tokens and no serif anywhere** — do
not "correct" our palette against it. You will be misled.

## Verify, don't recall

This project's entire defect history is one pattern: *a confident claim about an external
system that nobody executed.* Steel's JSON field names, Wikipedia's HTML, the Anthropic
model IDs — check them, and write down what you find. `docs/steel-json-shapes.md` exists
for exactly this.
