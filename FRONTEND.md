# Wikirace vs. Agent — Build Spec v3 (frontend + game)

**Supersedes `PLAN.md` for everything user-facing. `PLAN.md` §2 still owns the Python contracts.**
**Read `CLAUDE.md` first.** Then §0, then your lane in §9, then the sections your lane owns.

Anything marked *verified* was executed against the live service on 2026-09-12. Numbers without
that word are estimates and say so. This project's whole defect history is unexecuted confident
claims — so if you need a fact that isn't marked *verified*, go get it and write it down here.

---

## 0. Scope — read before anything else

`PLAN.md` §1 said, in bold: *"The human races on their own real laptop/browser. That is out of
scope for code."* That sentence was carrying roughly 40% of the new work. The human now races in
an app we write, so we own their article view, link interception, trail, move counter, win
detection — and the **referee**, because a machine now decides who won instead of a host with a
stopwatch.

| | v2 (merged) | v3 (this) |
|---|---|---|
| Python | ~900 LOC | ~950 (−150 `display.py`, +90 server, +50 events, +60 race) |
| TypeScript/TSX | 0 | **~1,400 LOC + ~250 lines CSS/config** |
| Toolchain | pip | pip + npm/Vite/Tailwind |
| Raw person-hours | ~5–6 | **~22** against ~24 capacity (3 × 8 productive) |

**22/24 is 93% utilization, which does not ship.** Hackathon estimates run low, not high. Make
these cuts now, not at 1 a.m. Each is a named file, not a vibe.

| Cut | Saves | Why it's safe |
|---|---|---|
| **`speedrun/display.py` + `test_display.py` — never create them** | 2.0h | The browser is the UI. §8 re-homes its two real obligations. |
| **Theme toggle + sound toggle — cut entirely, not stubbed** | 0.75h | §2.4. |
| **`Special:Random` → the curated pairs in §5.4** | 0.4h | *Verified:* `list=random&rnnamespace=0` returned *Syed Ali Shah Geelani* + *1320s in poetry*. Unwinnable on a projector. |
| Autocomplete dropdown → `<input list>` + `<datalist>` | 0.5h | Native, keyboard-accessible, zero ARIA work. |
| "All games" nav dropdown | 0.3h | Spec says optional; the reference's version is a multi-game nav we don't have. |
| `steel_client.py` → 4 functions (`start`/`navigate`/`content`/`stop`) | 0.5h | Arrival is detected by canonical title, not URL. |
| `banned_titles` / stuck-retry / 700ms second-look in `race.py` | 0.5h | A stuck hop now reads as a slow `thinking` state, not a false loss. |
| `tests/test_wiki.py` → fold 4 asserts into `test_links.py`. **Keep the fixture test.** | 0.6h | |
| Results collapsible paths → two plain `<ol>`s | 0.3h | |
| `--model claude-sonnet-5` — ship Haiku only *(but see §5.5: `hard` tier wants Sonnet)* | 0.3h | |
| Tie as a code path → a caption (§2.6) | 0.3h | |
| Motion polish — **time-box 45 min at CP4, cut if late** | 1.0h | |
| Responsive → `flex-col lg:flex-row` only, no other breakpoints | 0.5h | Satisfies the spec's stacking rule for free. |

**What you defend if everything goes wrong:** Setup (two validated inputs + difficulty + black
Start pill) → Race (one shared Fraunces timer, left = real clickable Wikipedia with trail and
counter, right = Steel live view + reasoning log, target badge) → Results (winner, giant number,
both paths, Race again). Agent driven by the real Steel/Claude loop if it lands, by `mockFeed` if
it doesn't. **The UI cannot tell the difference** — that's the point of §6.

---

## 1. What the spec gets right

Two calls are better than they look, and both survived measurement:

1. **"Make this panel's data source a clearly isolated module/interface so it's easy to swap a
   mock feed for a real agent later."** The best line in the spec. It turns the riskiest
   dependency in the project — Steel + an LLM + a cloud session over venue wifi — into a URL
   parameter. It's why two of three lanes are unblocked from minute 20 and why the demo survives
   the agent dying at 11 p.m.
2. **One shared timer that times both racers and stops when either lands.** Correct — and taking
   it seriously forces a fairness fix nobody would have found otherwise: you *cannot* start that
   clock on the Start click, because the agent's Steel cold start gets charged to it. Hence §2.6's
   two-phase start.

A third: mandating canonicalization against Wikipedia's real title/redirect independently
rediscovered `PLAN.md` §1's locked decision — the one `PLAN.md` says would have failed on stage.

---

## 2. Decisions — answered, not offered

### 2.1 Player's article view → **our own renderer, drawn into a same-origin iframe**

Framing Wikipedia *is* allowed. *Verified:* `GET /wiki/Cat` → `x-frame-options` count **0**, CSP
`frame-ancestors` count **0**. **That's a red herring.** A cross-origin frame is opaque, so the
parent can't read any of the four things the game needs continuously (current article, trail, move
count, win check). *Verified in real Chrome after a real in-frame click:*

| Parent attempts | Result |
|---|---|
| `iframe.contentWindow.location.href` | **SecurityError** |
| `iframe.contentDocument` | **`null`** — silently, no throw. This is the trap. |
| `performance.getEntriesByType('resource')` after the click | **unchanged** |
| `postMessage` received in 3.5s | **0** |
| `load` event | fires once — tells you "something happened" and nothing else |

Ruled out so nobody re-litigates at 1 a.m.: `postMessage` needs a cooperating child (Wikipedia
posts nothing); polling `location.href` throws every read; `load`-counting yields a blind counter
that also fires on redirects; a rewriting CORS proxy is the custom renderer *plus* a server.
Second independent ground: a cross-origin frame ships Wikipedia's own search box and
`Special:Random`, and you can't strip chrome from a frame you can't script.

**But do render into a `srcdoc` iframe** — same-origin, fully readable — for CSS isolation, and
it isn't optional. Wikipedia's content CSS contains **unscoped `a { color:#0645ad }`** plus ~169
other unscoped selectors; link it globally and your whole app goes Wikipedia blue. **Shadow DOM
does not fix this:** the payload carries **19–21 inline TemplateStyles `<style>` blocks**
(*verified: 19 on `Snake`, 0 `<script>`*) and 17–22 of their selectors are prefixed
`body.skin-vector-2022` / `body:not(.skin-minerva)` / `html.skin-theme-clientpref-*`. A shadow
root has no `body` ancestor, so infobox cells, navbox images, cladograms and reflist columns
silently break. A same-origin iframe gives real `<html>`/`<body>`, total isolation, **and** full
parent DOM access for click interception.

### 2.2 Article HTML → **`action=parse&prop=text`. Never `rest_v1/page/html`.** Blocker-class.

*Verified* — three flavors, three href forms:

| Source | absolute `https://en.wikipedia.org/wiki/` | `/wiki/` | `./Title` |
|---|---|---|---|
| read view (what `steel browser content` returns; our fixture) | **1,052** | 66 (chrome) | 48 |
| **`action=parse&prop=text`** ✅ | 0 | **1,268** | 0 |
| `api/rest_v1/page/html/` ❌ | 0 | 0 | **2,584** |

`PLAN.md` §4.A's frozen regex against all three yields **485 / 485 / 0**. REST silently produces
an empty move set — v1's blocker reborn in a second language. Pick `action=parse` because:

1. Its hrefs are the form the Python contract already accepts → **one mental model, two languages.**
2. It returns `parse.title` **already redirect-resolved** plus a `parse.redirects` array **in the
   same request**, so the win check costs zero extra round trips. *Verified:* `page=Snakes` →
   `title: "Snake"`; `page=WWII` → `"World War II"`; `page=NotARealArticleXyzzy` →
   `error.code: "missingtitle"`.
3. It's a **fragment** — no `<head>` to strip, no `<base>` to delete.
4. `disableeditsection=true` removes 132 edit links (*verified: 132 → 0*). `<script>` count **0**.
5. Smallest of the three: 582 KB on `Snake` vs 1.31 MB for `rest_v1` on `Cat`.

### 2.3 Backend → **yes, one Python file, ~90 lines, zero new dependencies**

The Wikipedia half needs **nothing**: all endpoints are CORS-open (*verified:
`access-control-allow-origin: *`*, including `api.php?…&origin=*`). The agent half can't live in
the browser — Vite inlines `import.meta.env.VITE_*` into the served bundle, so keys can't move
client-side, and `steel` is a CLI.

`PLAN.md` §1's *"No web backend, no database, no auth"* is **one-third dead, two-thirds alive.**

**SSE on stdlib `ThreadingHTTPServer`.** *Verified:* stream open **and** a second request served
concurrently in **1 ms** (plain `HTTPServer` blocks — that one word is the whole trick); headers
`Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`Access-Control-Allow-Origin: *` with `Origin: http://localhost:5173`, so `EventSource` needs no
proxy and no CORS library.

### 2.4 Theme toggle + sound toggle → **cut both**

A deviation from an explicit spec requirement, so: the spec supplies **one** 12-token palette with
no dark set, and a real dark theme needs a token rename across every component (the tokens are
*surface*-relative — `--text-on-dark`, `--text-on-light` — not theme-relative, so in dark mode
`--text-on-light` would have to hold a light value and every usage reads as a bug).

More decisively, **the article wells can't flip anyway.** *Verified on our committed fixture:* 29
inline `style=` colour/background declarations including `background: #FFCC55` ×5 and
`background-color: #EEEEEE` ×4; on live `Cat`, `style="color:white"` ×6. The two article panels
are ~70% of the Race screen and stay light in both themes. **A toggle that visibly does nothing to
most of the screen is worse than an absent toggle.** Re-add condition: hand me a second 12-hex
palette and it's ~40 minutes, scoped to app chrome only.

The sound toggle has no audio assets and no specified sounds. Same rule.

**This also fixes a contradiction in the spec.** It asks for "a black pill button far right" on
every screen *and* "no more than one solid black CTA visible at a time." Resolution: **the nav's
right-hand pill is `--surface-grey`, permanently.** `--accent-black` is reserved for the current
phase's single primary action, which makes black a reliable "press this" signal.

### 2.5 Steel's live view → **shown, prominent, embedded. It frames.**

Your decision, and *verified* it's buildable — probed `api.steel.dev/v1/sessions/{id}/player`
twice, independently, with no API key:

- HTTP/2 **200**, `content-type: text/html`, **65,906 bytes**, `<title>Steel Session Player (WebRTC)`
- **No `x-frame-options`. No `content-security-policy`.** → embeds in an iframe.
- Real query params: **`?interactive=false`** (read-only — use this; the agent pane must not be
  clickable by the audience) and **`?hideOverlay=true`**.
- **Not real:** `theme=light`, `showControls=false` — *verified 0 occurrences anywhere in the file*.
  Don't put them in the URL and don't believe a doc that says otherwise.
- Templated constants: `inputCoordinateSpace = {width:1920, height:1080}`; transport is WebRTC via
  `stun.cloudflare.com:3478` + 5 TURN URLs.

**Consequence: the agent panel does NOT also render the article with our renderer.** The live view
*is* the agent's article view. That deletes work and it's what you asked for. **What you're trading
away:** the spec's "both panels visually match so neither reads as more important." They won't
match — one is our typography on a warm well, the other is a video of Wikipedia's own blue-and-white
skin. Parity is recovered structurally instead: identical `--card-green` cards, identical radius,
identical header treatment, equal visual weight. Accept it; a real browser visibly driving itself
is a better demo artifact than parity.

⚠️ **Lane C must verify one thing at the probe:** that `live_url` from `steel browser start`
actually resolves to this `/player` endpoint, and `curl -I "$LIVE_URL"` still shows no
`x-frame-options`. Commit the output to `docs/steel-json-shapes.md`. The lifecycle doc warns
`connect_url` is display-safe-only — **never put `connect_url` on screen**; `live_url` is the one
that's safe to show.

**Fallback ladder** if that probe surprises us: (1) `?interactive=false` in an iframe ← default;
(2) second browser window beside the app, positioned by hand at rehearsal; (3) `steel browser
screenshot` polled through our server into an `<img>` at ~1 fps — ugly but alive; (4) our renderer
on the agent's article plus a "real Chrome, driven by Steel" badge.

**During the agent's thinking phase** (~1s LLM call) the live view shows a static page. Don't leave
it dead: the reasoning log below it gets a `◔ thinking…` row with the current article and its legal
link count, so the prominent pane always has motion somewhere.

### 2.6 The clock → **browser-side, `performance.now()`, two-phase start**

```ts
// The ONLY clock. Monotonic, immune to system-clock changes.
export const elapsedMs = (t0: number) => performance.now() - t0;
```

**Never accumulate `setInterval` ticks.** Background tabs clamp `setInterval` to ≥1s and suspend
`rAF` entirely, so a projector operator switching tabs would desync the official race clock. `rAF`
repaints digits; it does not measure time. *(The spec says "setInterval/rAF-driven" — this is a
correction, not a preference.)*

**Two-phase start, mandatory.** The spec starts the timer "the instant Start Race is pressed,"
which charges the agent for a Steel cold start — a number `PLAN.md` §4.E itself says has never been
measured — plus the player's own 0.3–0.5s first fetch.

```
ready --[Start Race]--> arming ----------------------> 3..2..1 --> GO --> racing
                          ↑ waits for BOTH: player's start article fetched+painted,
                            and the agent's `ready` event (Steel up, parked on start)
                          ↑ 20s budget, then ARM_FAILED → back to setup
```

`POST /race/{id}/go` is the gun; both `t0`s are set on one HTTP round trip, so skew is bounded by
RTT/2 — *measured at 0.40 ms on loopback* (median RTT 0.325 ms over 30 trials).

**Three referee rules:**
1. **Adjudicate on event timestamps, never arrival order.** The agent's hop *happened* before its
   SSE frame *arrived*. The display may tick past a winning moment and snap back ~50 ms. **That is
   correct, not a glitch.**
2. **The player's timestamp is stamped at CLICK, not at fetch-resolve.** *Verified:* a parse fetch
   is 0.5–1.0s here and 2–4s on bad wifi. Stamping at resolve would make the player's clock 6× the
   tie window slower than the agent's.
3. **Never reverse an announced winner on a projector.**

**Ties are not a code path** (spec deviation, flagged). A player click and an SSE frame landing in
the same frame is vanishingly rare, and `RaceResult.winner` is already `"bot" | "human" | "none"`
with no `"tie"`. First-by-timestamp wins; if the margin is under 1.0s, Results adds a caption:
**"Photo finish — won by 0.4s"**. That's better television than a tie anyway.

### 2.7 Mid-race reload → **not supported** (your call)

Delete: `sessionStorage` snapshots, reload recovery, trail rehydration. **Do NOT delete
replay-on-connect** — the server replaying its full event log to a new subscriber is load-bearing
for the *initial* connect (the browser subscribes after `POST /race`, and without replay it misses
the `ready` event and arming hangs forever). Keep `seq` dedupe for the same reason.

If the user reloads anyway — and they will — the app shows a plain in-palette "Race abandoned →
Back to setup", and the dropped SSE stream makes the server `POST /stop` its own run. **A leaked
Steel session is the one unacceptable outcome**; the `try/finally` in `PLAN.md` §4.E covers it and
stays non-negotiable.

---

## 3. Design system

### 3.1 What the reference screenshot settled

The screenshot (dialed.gg/color) arrived after the analysis. It **confirms** that dialed.gg is a
**white page, near-black card, all-grotesque** design with **no serif anywhere** and none of our
twelve tokens. **Our palette and Fraunces are an original adaptation — do not "correct" them
against the live site.** Put that in the README; anyone who checks will be misled.

What it *did* settle — the composition, which prose couldn't:

| Observed | What we adopt |
|---|---|
| One **tall portrait card** centered on the page (~630×820 at 2000px viewport → ~31% vw, aspect ~0.77) | Setup and Results are portrait hero cards, not wide landscape ones |
| **Content inside the card is LEFT-aligned** (the *card* is centered, its contents are not) | Left-align hero content. The spec's "big centered card" means the card, not the text. |
| Display word huge, **lowercase**, tight leading, top-anchored, ~90px on that card | `Wikirace the Agent` set lowercase, tight, top-left of the hero |
| Body copy in short paragraphs below, generous line height | |
| **Controls pinned to the card's bottom** under a small question-label ("Solo or multiplayer?") | Setup's pickers + difficulty sit at the card bottom under `Where to where?` |
| Nav: wordmark left, ghost icon buttons (no resting fill), black pill right | §4.1, minus the cut toggles |
| **A difficulty control exists** — small switch labelled "Easy", bottom of card | Direct precedent for §5.5. Three states need a segmented pill, not a switch. |
| Primary action is a large **circle**, not a pill | ⚠️ Your spec says "solid black pill" — **spec wins**, but the circle is available if you want closer fidelity |
| Footer links tiny, bottom-right | |

**Still guessed** (the screenshot is the intro screen, so it has no timer): the Results "giant
digit treatment" — no size, no relationship to the card. Default `min(150px, 30vw)`, MM:SS, on an
otherwise near-empty hero. Also guessed: exact shadow spread/alpha, and hero radius (using **32px**,
the top of your stated range). All three are single CSS variables — `--radius-hero`,
`--shadow-hero`, `--size-result` — so a later screenshot is a 60-second reconciliation.

**One rule for tonight:** if a decision needs an image you don't have, pick the value that's
conservative in the palette's direction (smaller radius, softer shadow, more negative space) and
leave `/* unverified: no reference for this state */`.

### 3.2 Palette — six changes, flagged because they edit values you specified

Every ratio below was computed (WCAG 2.x relative luminance). **Five of thirteen implied pairings
fail AA for normal text, and both muted tokens are implicated** — the textbook failure of a muted
editorial palette.

| # | Change | From → To | Reason |
|---|---|---|---|
| 1 | `--text-on-light-muted` | `#6E756C` → **`#585E56`** | #6E756C is **4.02 / 3.68 / 3.74 / 3.21** on bg-page / page-alt / grey / grey-dark. AA needs 4.5 — **all four fail**, and it's your most-used token (Setup subheading, every label, "Seconds to finish", the stats row). #585E56 keeps the hue (106.7°) and 4% saturation, lightness 0.441→0.353: **5.64 / 5.16 / 5.25 / 4.50**. Keep `#6E756C` as `--text-on-light-subtle`, legal at ≥18.66px only. |
| 2 | **ADD** `--text-on-dark-muted-soft: #C5CBC3` | new | `#A7B0A5` is **4.63** on `--card-green` (passes) but **3.33** on `--card-green-soft` (fails). Darkening the surface can't rescue it — you'd need `#34453C`, which is **1.02** against card-green, i.e. the "lighter green" stops being lighter. #C5CBC3 is **4.51** / **6.26**, so you may standardise on it and carry one muted token. |
| 3 | Pill inputs move **inside** a `--card-green` card | no hex change | `#E7E4DD` on `#F3EBE0` is **1.07**. WCAG 1.4.11 needs 3.0 for a control boundary, and no in-palette border rescues it (`--surface-grey-dark` 1.25, `--divider` 1.26). On `#33443A` it's **8.15**. **Never put a bare grey pill directly on the beige page.** |
| 4 | **ADD** `--surface-well: #FAF6EF` | new | The article reading well. **13.93** for body ink. Resolves the spec's own "pick one consistent surface color": both panels are identical `--card-green` cards containing identical light wells. Wikipedia ships hundreds of light-background-assumed fills and transparent-PNG diagrams with no safe recolouring pass. |
| 5 | **ADD** `--focus-ring: #171717`, `--focus-ring-on-dark: #F3F1EA` | new | The spec defines no focus ring, and borderless shadow-only pills are exactly where the default ring gets suppressed. `#171717` is **15.17** on page but **1.73** on card-green, so one token isn't enough. |
| 6 | **ADD** `--error: #934535`, `--error-on-dark: #E0A292` | new | Spec mandates "muted red-brown, in-palette" and gives no hex. `#934535` (H 12°, S 47%, L 39%) is **5.65 / 5.26 / 4.51** on light surfaces but **1.55** on card-green — where change 3 puts the Setup errors. You need both. |

Unchanged and verified fine: `--text-on-light #232823` (12.70 / 11.82 / 13.93); `--text-on-dark
#F3F1EA` (9.16 on green, **15.86** on accent-black); `--card-green` on page (8.76).
⚠️ `--card-green-soft` vs `--card-green` is **1.39**, so a hover built only on that swap is
invisible — pair it with a shadow or a divider.

### 3.3 Fraunces has no tabular figures, and the timer will jitter

**`font-variant-numeric: tabular-nums` and `font-feature-settings: "tnum" 1` are silent no-ops on
Fraunces.** Its OpenType feature list is exactly `['kern','liga','rvrn']` — no `tnum`, no `lnum`,
no `.tf` alternates. And its proportional digits are badly uneven at display sizes: in the file the
§3.4 URL actually serves (SOFT pinned to 50), at `wght 500 / opsz 92` the widest digit `0` is
**0.6288em**, narrowest `1` is **0.3951em**, colon **0.2589em**. At 92px that's **~21.5px of jump
per digit position and ~86px of MM:SS swing, re-centering every second**, on the one element
everybody is staring at.

**Fix — fixed-width digit slots.** Use **0.64em / 0.28em**, not the 0.62/0.24 that a range-axis
measurement suggests (pinning SOFT changes the metrics and both slots would end up narrower than
their glyphs):

```tsx
// TimerDigits.tsx — one <span> per character, each in a fixed slot. Lane A.
const W_DIGIT = "0.64em", W_COLON = "0.28em";
export function TimerDigits({ ms }: { ms: number }) {
  const s = Math.floor(ms / 1000);
  const txt = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  return (
    <span className="font-display tabular-slots" aria-label={`${txt} elapsed`}>
      {[...txt].map((c, i) => (
        <span key={i} style={{ display: "inline-block", width: c === ":" ? W_COLON : W_DIGIT,
                               textAlign: "center" }}>{c}</span>
      ))}
    </span>
  );
}
```

### 3.4 Fonts

Fraunces is a variable font with `SOFT`, `WONK` and optical-size axes. Pin `SOFT` and `WONK` so the
served file is deterministic (that's what the 0.64em slot was measured against):

```html
<!-- index.html. Lane A owns this file. -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,400..600,50,0;1,9..144,400..600,50,1&family=Inter:wght@400;500;600&display=swap">
```

- Giant timer / hero display: `font-variation-settings: "opsz" 92, "SOFT" 50, "WONK" 0;`
- Flavor italic captions: the `ital 1` + `WONK 1` axis pair — that's the "slight italic wonk" the
  spec asks for. Use it on captions only, never on the timer.

### 3.5 `web/src/styles/theme.css` — Tailwind **v4**

⚠️ `npm i tailwindcss` today gives you **v4**, which is a **Vite plugin**. There is no
`tailwind.config.js`, no `postcss.config.js`, and `npx tailwindcss init -p` does not exist. Anyone
reaching for a v3 config file is about to lose 30 minutes.

```css
/* web/src/styles/theme.css — FROZEN in the prologue. Token block is not Lane A's to change. */
@import "tailwindcss";

@theme {
  --color-bg-page:            #F3EBE0;
  --color-bg-page-alt:        #EFE0D2;
  --color-card-green:         #33443A;
  --color-card-green-soft:    #445A4E;
  --color-surface-grey:       #E7E4DD;
  --color-surface-grey-dark:  #D8D4CA;
  --color-surface-well:       #FAF6EF;  /* §3.2 change 4 */
  --color-text-on-dark:       #F3F1EA;
  --color-text-on-dark-muted: #C5CBC3;  /* §3.2 change 2 */
  --color-text-on-light:      #232823;
  --color-text-on-light-muted:#585E56;  /* §3.2 change 1 */
  --color-text-on-light-subtle:#6E756C; /* ≥18.66px ONLY */
  --color-accent-black:       #171717;
  --color-divider:            #DAD3C6;
  --color-error:              #934535;  /* §3.2 change 6 */
  --color-error-on-dark:      #E0A292;

  --font-display: "Fraunces", ui-serif, Georgia, serif;
  --font-body:    "Inter", ui-sans-serif, system-ui, sans-serif;

  --radius-hero: 32px;   /* guessed — see §3.1 */
  --radius-card: 24px;
  --radius-pill: 999px;

  --shadow-hero: 0 24px 64px -16px rgb(70 52 32 / 0.18), 0 2px 8px -2px rgb(70 52 32 / 0.10);
  --shadow-card: 0 12px 32px -12px rgb(70 52 32 / 0.14);
}

:root { --size-result: min(150px, 30vw); }   /* guessed — see §3.1 */

body {
  background: linear-gradient(168deg, var(--color-bg-page) 0%, var(--color-bg-page-alt) 100%);
  color: var(--color-text-on-light);
  font-family: var(--font-body);
}
.font-display { font-family: var(--font-display); font-variation-settings: "SOFT" 50, "WONK" 0; }
.tabular-slots { font-variation-settings: "opsz" 92, "SOFT" 50, "WONK" 0; letter-spacing: 0; }
:where(a, button, input, [tabindex]):focus-visible {
  outline: 2px solid var(--color-focus-ring, #171717); outline-offset: 3px;
}
.on-dark :where(a, button, input, [tabindex]):focus-visible { outline-color: #F3F1EA; }
```

---

## 4. Component inventory

### 4.1 Shared chrome — **Lane A**
| Component | Notes |
|---|---|
| `TopNav` | wordmark left (Inter 500), one **grey** pill right (§2.4). No theme/sound icons. |
| `Pill` | `variant: "black" \| "grey" \| "ghost"`, `size: "sm" \| "md"`. Everything imports this — build it first. |
| `Card` | `tone: "green" \| "light"`, `radius: "hero" \| "card"`, shadow, no border. |
| `TitleInput` | `<input list>` + `<datalist>`, 350ms debounce, `InlineError` slot. |
| `InlineError` | `--error-on-dark` inside a green card. |
| `TimerBar`, `TimerDigits` | §3.3. |

### 4.2 Setup — **Lane A**
One portrait hero card, content left-aligned (§3.1). Lowercase Fraunces title, muted Inter
one-liner, then pinned to the card bottom under a small label: `DifficultySegment`, two
`TitleInput`s prefilled from the tier's default pair, a ghost `Randomize` pill, and one black
`Start Race` pill — disabled until both titles resolve to real, distinct articles.

### 4.3 Race — **Lane B** (except `TimerBar`, Lane A)

Two columns; the right one stacked, because the live view is the only fixed-aspect (16:9) element
and stacking is the only arrangement that gives it a *wide* slot instead of a tall narrow one.
Geometry at 1920×1080, Chrome fullscreen, 100% zoom (**a hard prerequisite — rehearse it**):

```
header  1920 × 112   full-bleed, --card-green
body    y112..1056   columns: 20 + 896 + 16 + 968 + 20 = 1920
right stack: 968×544 (live view, exact 16:9) + 16 + 968×368 (reasoning log) = 928
```

```
╔═══════════════════════════════════════════════════════════════════════════════════╗
║  RACING · MEDIUM · HOP 3/25          02:41           Coffee ──▶ Barack Obama      ║ 112
╚═══════════════════════════════════════════════════════════════════════════════════╝
 ┌─────────────────────────────────────┐  ┌────────────────────────────────────────┐
 │ YOU · Coffee · 386 legal links      │  │ AGENT'S BROWSER — LIVE              ●  │
 │ ─────────────────────────────────── │  │  ┌──────────────────────────────────┐  │
 │                                     │  │  │  Steel live view iframe          │  │
 │  Coffee is a beverage brewed from   │  │  │  ?interactive=false              │  │ 544
 │  roasted, ground coffee beans…      │  │  │  968 × 544, exact 16:9           │  │
 │                                     │  │  └──────────────────────────────────┘  │
 │  ◦ John Adams  ← target highlighted │  └────────────────────────────────────────┘
 │                                     │  ┌────────────────────────────────────────┐
 │  672px prose column (42rem)         │  │ AGENT REASONING                        │
 │  896px panel, 832 content           │  │ 1  0:01.9  Coffee ─▶ "Brazil"          │ 368
 │                                     │  │ 2  0:05.4  Brazil ─▶ "United States"   │
 │  Coffee → Brazil → …      HOPS 2    │  │ ◔  thinking · Barack Obama · 1204 links│
 └─────────────────────────────────────┘  └────────────────────────────────────────┘
```

**Minimum readable article column: 672px of running text** = 42rem at 17.5px Inter ≈ 78ch. That's
above the 45–75ch reading ideal on purpose — the player is *scanning for a link*, not reading
prose, and every extra character per line is one less scroll. Plus 32px padding either side and a
16px scrollbar gutter → **736px is the floor**; we allocate 896px, leaving 160px of headroom for
infoboxes and wide tables.

⚠️ **Deviation I'm making from the analysis:** one specialist proposed a 128px header with four
rows of keyboard hints (`[SPACE] GO`, `[A] AUTOPILOT`, …). That's a gamer HUD and it fights the
"soft, minimal, editorial, lots of negative space" language your spec and the screenshot both ask
for. I've cut it to a single 112px row: phase · difficulty · hop count on the left, the timer
centered as the focal element, the route on the right. Keyboard hints live behind the nav's
`How it works` pill.

Components: `PlayerPanel` (wraps `ArticleFrame`), `AgentPanel` (wraps the live-view iframe),
`AgentLog`, `PathTrail`, `TargetBadge`.

### 4.4 Results — **Lane A**
Portrait hero card again. Lowercase Fraunces headline, `--size-result` MM:SS number, muted Inter
caption, a stats row (your time + hops vs the agent's), two plain `<ol>` paths, then a black
`Race again` pill and a ghost `New articles` pill.

**Six outcomes, not two.** The spec designs for "You won / Agent won"; `PLAN.md` §4.D's
`announce_result` obligation requires all of them, each with `elapsed_s`:

⚠️ **A WINNER OUTRANKS THE AGENT'S STOPPING REASON. Test `winner` FIRST, then `reason`.**
CORRECTED 2026-09-12 — this table used to be keyed on `reason` alone, and Lane A implemented
it exactly as written, which was the right reading of the wrong spec. `hop_limit_reached` and
`dead_end` say why the **agent** stopped; §7 keeps the human racing afterwards, so those two
reasons can ONLY ever reach this screen alongside a human win. Keying the headline on `reason`
therefore printed *"The agent gave up"* in 48px to a player who had just won, with the words
"You won!" nowhere on screen. The agent's give-up is not lost — it belongs in the stats row
("Agent · N hops · gave up"), not the headline. Pinned by `gameStore.referee.test.tsx`.

| Condition, in this order | Headline | Note |
|---|---|---|
| `winner:"human"` | **You won!** | whatever `reason` holds — including a preserved `hop_limit_reached`/`dead_end` |
| `winner:"bot"` | **Agent won!** | |
| `reason: "error"` | **Race ended early** | host-readable message, never a stack trace |
| `reason: "hop_limit_reached"` | **The agent gave up** | only with `winner:"none"`, i.e. nobody reached the target |
| `reason: "dead_end"` | **The agent hit a dead end** | `NoCandidatesError`, same caveat |
| `reason: "human_finished_first"` | **You won!** | backstop; `winner` above normally catches this first |

The caption under the clock is **not** a photo-finish margin. `marginMs` is null in every
stageable race — see §10 R5's amendment, which supersedes the "won by 0.4s" line this table
used to advertise. `Results.tsx` keeps the `marginMs < 1000` branch as defensive code only.

---

## 5. Wikipedia data layer, renderer, and pairs

### 5.1 Endpoints — `web/src/lib/wikiApi.ts` (**Lane A**). Nothing else may talk to wikipedia.org.

```ts
const API = "https://en.wikipedia.org/w/api.php";
const enc = (t: string) => encodeURIComponent(t.replace(/ /g, "_"));

// Article HTML fragment + already-redirect-resolved canonical title. §2.2.
export const parseUrl = (t: string) =>
  `${API}?action=parse&page=${enc(t)}&prop=text&redirects=1&disableeditsection=true` +
  `&format=json&formatversion=2&origin=*`;

// Batch canonicalize/validate up to 40 titles.
export const canonUrl = (ts: string[]) =>
  `${API}?action=query&titles=${ts.map(enc).join("|")}&redirects=1` +
  `&format=json&formatversion=2&origin=*`;

// Autocomplete. opensearch is 537 B vs 3,213 B for rest.php/v1/search/title — that's the reason,
// not freshness (both are cache-control: max-age=10800).
export const searchUrl = (q: string) =>
  `${API}?action=opensearch&search=${encodeURIComponent(q)}&limit=8&namespace=0` +
  `&format=json&origin=*`;
```

⚠️ **Two bugs that were in the first draft of this module — don't reintroduce them.**

**(a) The normalization key.** `enc()` sends spaces as underscores, so the API's
`normalized[].from` comes back as `"barack_obama"`. Looking it up with the raw spaced string misses
and falls through to a lookup that can never hit — which left `Start Race` **permanently disabled
behind a false "No such article"** for any hand-typed multi-word title. *Reproduced:*
`validate("barack obama", "Napoleon")` → `{ok:false, field:'start', msg:'No such article.'}`.

```ts
const key = (t: string) => String(t).replace(/ /g, "_");
const resolve = (t: string, m: Map<string, string>) => {
  const x = m.get(key(t)) ?? m.get(t) ?? t;
  return m.get(x) ?? x;            // redirects can chain once
};
```

**(b) No `res.ok` check anywhere.** *A real 429 was hit against Wikipedia during this analysis, and
again by the pair-measurement script.* Unchecked, a 429's `text/plain` body flows into
`res.json()` → SyntaxError → unhandled rejection → **the button silently does nothing**; mid-race
it flows into `DOMParser`, the extractor returns an empty Map, `parse.title` is undefined, and
**the win check can never fire** — the race dead-ends on the projector with no diagnostic. Every
fetch in this module needs `if (!res.ok) throw new WikiError(res.status)`, a **Map cache** keyed by
canonical title, and a **concurrency cap of 3**.

### 5.2 `ArticleFrame.tsx` — **Lane B.** Same-origin iframe, delegated interception.

Write the fragment into a `srcdoc`/`document.write` iframe with the article CSS **inlined once**
(not `<link>`ed — a `<link>` in a freshly written document makes hop 1 flash unstyled at exactly
the moment the race starts). Then delegate one click listener on the frame's body:

```ts
frameDoc.body.addEventListener("click", (e) => {
  const a = (e.target as HTMLElement).closest("a[href]") as HTMLAnchorElement | null;
  if (!a) return;
  e.preventDefault();                                   // always, even for illegal links
  const m = /^(?:https?:\/\/en\.wikipedia\.org)?\/wiki\/([^?#]+)$/.exec(a.getAttribute("href")!);
  if (!m) return;
  const title = decodeURIComponent(m[1]).replace(/_/g, " ");
  if (!candidates.has(title)) return;                   // ← THE GATE. See below.
  onMove({ title, anchorText: a.textContent!.trim() });
});
```

⚠️ **`candidates.has(title)` is not optional.** The first draft called `onMove` for *any* surviving
anchor and relied on CSS `display:none` to enforce legality — and the hide list didn't match the
exclusion list. *Measured visible-and-clickable-but-illegal links: **Python (programming language)
157**, Roman Empire 68, Pizza 20, Cat 13* — and on our own demo page 151 of those 157 are the
single `.sidebar` block `PLAN.md` §4.A calls out by name. Worse, MediaWiki's collapsing is
JS-driven and we load no JS, so that sidebar renders **fully expanded**: 155 links spilling across
a soft editorial card. **Make the hide list *be* the exclusion list, and gate the handler on the
candidate set.** Two mechanisms, same source of truth.

### 5.3 `links.ts` — **Lane B**, and the *same person* writes `speedrun/links.py`

One rule, two languages. **The game's legal move set** = in-body article links, excluding:

```
.navbox, .sidebar, .side-box, .sistersitebox, .metadata, .portalbox, .navbar,
.mw-collapsed, .noprint, [hidden],
.reference, ol.references, .reflist, .mw-references-wrap, .mw-editsection
```
plus non-article namespaces (`File: Category: Special: Help: Portal: Template: Module: Draft:
User: Wikipedia: MediaWiki: TimedText: Book: Talk:` and `_talk:` variants), plus `#cite_note` /
`#cite_ref` hrefs, plus self-links.

**Keep `.infobox`** (69 legitimate links on the Python page) and **keep `.hatnote`** — hatnotes are
body content and frequently literal inline "See also:" lines, i.e. exactly the lateral move that
wins races. A grep gate in §10 enforces both.

Two asymmetries found by measurement that must be fixed in **both** implementations, or one racer
gets moves the other doesn't:
- The frontend list must **add** `.reference, ol.references, .reflist, .mw-references-wrap` —
  otherwise the player gets 67 extra titles on `Cat` and 218 on `Roman Empire`, including
  race-winning hubs like `BBC News`.
- `speedrun/links.py` must **add** `.noprint`.

Why the exclusion matters at all: it shrinks the move set by **45–72%**. Any hop-distance number
computed over all `/wiki/` links is wrong for this game.

### 5.4 `pairs.ts` — **Lane A.** Measured, not guessed.

Measured today with a rate-limited script under the §5.3 rule. **Soundness contract: `hops: 2` is
EXACT** (proven by fetching the real move sets of start and intermediate); **`hops: 3` means
*proven not 1 and not 2*** — exact depth beyond 2 was not determined, and the type says so. No
pair is a 1-hop gimme (that's a 3-second race). `fanout` = the start article's legal move count;
low fanout means fewer obvious routes, which is the second difficulty lever.

```ts
export type Pair = { start: string; target: string; hops: 2 | 3; atLeast?: true; fanout: number };

export const PAIRS: Record<Difficulty, Pair[]> = {
  // 2 hops, high fanout — many routes. The human can win while narrating.
  easy: [
    { start: "Cat",      target: "Napoleon",            hops: 2, fanout: 472 }, // via Ancient Egypt
    { start: "Chess",    target: "Antarctica",          hops: 2, fanout: 537 },
    { start: "Honey",    target: "Saturn",              hops: 2, fanout: 419 },
    { start: "Tea",      target: "Basketball",          hops: 2, fanout: 415 },
    { start: "Banana",   target: "Jazz",                hops: 2, fanout: 414 }, // via Africa
    { start: "Guitar",   target: "Albert Einstein",     hops: 2, fanout: 349 },
    { start: "Bicycle",  target: "William Shakespeare", hops: 2, fanout: 322 }, // via Coventry
  ],
  // 2 hops but narrow, or >=3 with room to manoeuvre.
  medium: [
    { start: "Sushi",     target: "Volcano",       hops: 2, fanout: 299 },
    { start: "Umbrella",  target: "Tsunami",       hops: 2, fanout: 289 }, // via Japan
    { start: "Pizza",     target: "Mars",          hops: 2, fanout: 204 }, // via Campania
    { start: "Waffle",    target: "Tornado",       hops: 2, fanout: 125 },
    { start: "Violin",    target: "Glacier",       hops: 3, atLeast: true, fanout: 350 },
    { start: "Coffee",    target: "Mount Everest", hops: 3, atLeast: true, fanout: 312 },
    { start: "Chocolate", target: "Samurai",       hops: 3, atLeast: true, fanout: 312 },
  ],
  // >=3 hops AND low fanout — genuinely hard for a human under pressure.
  hard: [
    { start: "Origami",    target: "Submarine",  hops: 3, atLeast: true, fanout: 144 },
    { start: "Pencil",     target: "Kangaroo",   hops: 3, atLeast: true, fanout: 185 },
    { start: "Lighthouse", target: "Dinosaur",   hops: 3, atLeast: true, fanout: 215 },
    { start: "Soap",       target: "Jupiter",    hops: 3, atLeast: true, fanout: 224 },
    { start: "Bread",      target: "Black hole", hops: 3, atLeast: true, fanout: 240 },
    { start: "Penguin",    target: "Sahara",     hops: 3, atLeast: true, fanout: 256 },
  ],
};

// Redirect regression fixtures — NOT for the demo. These are what R4 in §10 uses.
export const REDIRECT_FIXTURES = [
  { typed: "Snakes", canonical: "Snake" },
  { typed: "WWII",   canonical: "World War II" },
  { typed: "Obama",  canonical: "Barack Obama" },
];
```

**No target appears more than once across all 20 pairs** — checked, because the earlier 14-pair set
had 6 of 14 targeting *Roman Empire*, which on the 3–5 runs a demo actually does would have landed
on the same target more than half the time.

### 5.5 The difficulty system

Difficulty moves **two honest levers** — the pair and the agent — and **no artificial handicap.**
A per-hop delay would be the most controllable lever and the least defensible; if a judge asks
"is it slowed down?", the answer has to be no.

| Tier | Pair | Model | Settings | `find_target` | Expected |
|---|---|---|---|---|---|
| **Easy** | 2 hops, fanout ≥320 | `claude-haiku-4-5` | `temperature=0`, `max_tokens=300` | **off** | agent ~25–35s; a narrating human beats it |
| **Medium** | 2 hops narrow, or ≥3 | `claude-haiku-4-5` | same | on | close race |
| **Hard** | ≥3 hops, fanout ≤260 | `claude-sonnet-5` | ⚠️ `thinking={"type":"disabled"}` **or** adaptive + `effort:"low"` + `max_tokens=2000` | on | agent looks strong |

⚠️ **The `hard` tier is the only thing in v3 that needs the Sonnet path, and `PLAN.md` §2.4 warns
it is broken as written:** Sonnet 5 runs adaptive thinking when `thinking` is omitted, and
`max_tokens` caps thinking + response *together*, so `max_tokens=300` truncates before the
`choose_link` block lands and the fallback fires on **every** hop — a 100%-fallback bot that still
*looks* like it's working. Apply the fix or ship `hard` on Haiku. This is why the cut list only
half-cuts the Sonnet path.

Turning `find_target` **off** for easy is the cleanest honest weakening: the agent stops taking a
guaranteed one-hop win it can see, which is a real capability difference, not a stopwatch trick.
Label it in the UI: `Easy — the agent doesn't look ahead`.

**UI:** a segmented pill (`Easy | Medium | Hard`) at the bottom of the Setup card, left of the
article inputs, following the reference's control-plus-label treatment (§3.1). Default **Medium**.
Picking a tier fills both inputs from a random pair in that tier. The host may still type anything;
typed pairs run at the **currently selected** tier's agent settings, and the UI says so.

---

## 6. The event schema — the one cross-lane contract

### 6.1 `web/src/agent/types.ts` — **FROZEN in the prologue.** This is the new `types.py`.

```ts
export type Difficulty = "easy" | "medium" | "hard";
export type Winner = "bot" | "human" | "none";   // same three literals as RaceResult.winner.
                                                 // Adopt verbatim — no mapping layer can then
                                                 // invert a result on a projector.
export type AgentEvent =
  | { seq: number; t: "ready";    at: number; session_id: string; live_url: string }
  | { seq: number; t: "thinking"; at: number; article: string; n_candidates: number }
  | { seq: number; t: "pick";     at: number; from: string; to: string;
      anchor_text: string; reason: string; was_fallback: boolean }
  | { seq: number; t: "arrive";   at: number; article: string; hop: number }
  | { seq: number; t: "done";     at: number; reason: "won" | "hop_limit_reached" | "dead_end" | "error";
      hops: number; message?: string }
  | { seq: number; t: "error";    at: number; message: string; fatal: boolean };

export interface AgentFeed {
  subscribe(on: (e: AgentEvent) => void): () => void;   // returns unsubscribe
}
```

`anchor_text` is **required, not decorative.** It carries `PLAN.md` §4.D's obligation: because the
agent navigates rather than clicks, our extractor is what proves the link existed — so the log must
name the anchor text as it appeared. It's what shows a judge the agent moved through a real link.

### 6.2 `mockFeed.ts` — **Lane A. Build this BEFORE the Setup screen.**

The highest-leverage file in the project. It's what unblocks Lanes A and B from Python entirely,
and it's the stage fallback if Steel dies.

```ts
export function mockFeed(pair: Pair, speed = 1): AgentFeed { /* scripted hops, realistic gaps */ }
export function makeFeed(pair: Pair): AgentFeed {
  return new URLSearchParams(location.search).get("agent") === "real"
    ? sseFeed("http://127.0.0.1:8848") : mockFeed(pair);
}
```

**Every scripted hop must be a legal move** under §5.3 — verify against a real fetch once, or the
mock teaches you a bug that doesn't exist. Route via a known-good intermediate from §5.4.

---

## 7. State machine, referee, server

```
setup → validating → arming → countdown → racing → finished
          ↑ both titles canonical & distinct        ↓ first canonical-title match, by TIMESTAMP
          ↓ inline error                      ┌─────┴─────────────────────────┐
        setup                                 │ agent hop_limit / dead_end:   │
                                              │ agent panel says "gave up",   │
                                              │ THE HUMAN KEEPS RACING        │
                                              └───────────────────────────────┘
```

`gameStore.ts` (**Lane A**) is the referee. It owns: both trails, both hop counts, `t0`, the win
check, and the single `finished` transition. `Race.tsx` (Lane B) consumes it read-only via
`useGame()` and calls exactly one action: `playerNavigated({ title, anchorText })`. Lane A wires
the agent feed in `App.tsx`.

⚠️ **`PLAN.md`'s hop limit 25 has a hole the spec never covers: what happens when the agent gives
up and the human is still clicking.** The race does **not** end. The agent panel shows a calm
in-palette "gave up after N hops", the clock keeps running, and the human can still win. §4.4 has
the copy.

`speedrun/server.py` (**Lane C**, ~90 lines, stdlib, bind `127.0.0.1`): `POST /race` starts a run,
`POST /race/{id}/go` is the gun, `GET /events` is the SSE stream **replaying the full log on
connect** (§2.7), `POST /stop` kills the run and the Steel session, `GET /health` returns
`{ok, anthropic_key, steel}`.

`speedrun/race.py` changes in six places: takes canonical titles; emits §6.1 events via an `emit`
callback; waits on a `go` flag; checks a `stop_flag` each hop; prewarms the Steel session during
Setup (see the §8 note on trap 4); keeps `NoCandidatesError → dead_end`.

---

## 8. What of `PLAN.md` v2 is dead

**Amend `PLAN.md`, don't rewrite it.** A rewrite is 45–60 minutes on the critical path, and its
most valuable prose — §2.4's Claude contract, §4.A's blocker with its measurements, §2.3's traps,
§4.C's `link_index` warning, §3's probe post-mortem — is 100% intact and 100% still correct. A
rewrite risks paraphrasing exactly the paragraphs that stop a defect being rediscovered.

| §1 locked decision | Status |
|---|---|
| human vs. bot | **KEEP — strengthened.** Now literally true and machine-adjudicated. |
| *human races on own laptop, out of code scope* + *finish called manually* | **DELETE, both halves.** The biggest change in the project. There is no host and no Enter key; the referee is `gameStore.ts`. |
| Steel drives the bot | **KEEP — narrowed.** Only Lane C needs `steel` installed. |
| Claude picks the link | **KEEP verbatim.** §2.4 and §4.C survive whole. |
| host types endpoints, *"no randomization logic needed"* | **AMEND — inverted.** Randomize is now required; curated pairs (§5.4), not `Special:Random`. |
| win check on **canonical title**, not URL | **KEEP — promote to both racers.** Player from `parse.title`; agent from `<link rel="canonical">`. |
| bot **navigates**; extractor enforces legality; log names anchor text | **KEEP — now symmetric.** One rule, one mechanism, two racers. |
| 3-pane projector layout | **DELETE.** One fullscreen browser window. **New physical requirement: the demo machine needs a mouse and keyboard for the human** — one README line. |
| Language: Python | **AMEND.** Two languages meeting at exactly one interface: §6.1 over SSE. |
| *"No web backend, no database, no auth"* | **AMEND — one third dies** (§2.3). Still no database, still no auth, keys still server-side. |

| §2/§4 section | Status |
|---|---|
| §2.1 five dataclasses | **ALL FIVE SURVIVE, ZERO EDITS.** `RaceResult.winner` was already `"bot"\|"human"\|"none"`. |
| §2.2 `links/wiki/picker/steel_client` | **KEEP.** `links.py` gains a TS twin (§5.3), same author. `steel_client.py` shrinks to 4 functions. `picker.py` untouched. |
| §2.2 `display.py` (9 signatures) | **DELETE ALL NINE.** Replaced by `speedrun/console.py`, ~40 lines, one stderr line per event, for Lane C's own debugging. |
| §2.3 Steel commands + 3 traps | **KEEP every line.** Add **trap 4:** prewarming means `--session-timeout` now runs from the *Setup screen*, so `--inactivity-timeout 0` graduates from safety flag to routinely-exercised path. Re-prewarm on a background timer at 0.8× and re-emit `ready`; **never** recreate a session synchronously inside `POST /go` — that puts an untimed cold start back inside the race clock. |
| §2.4 Claude tool contract | **KEEP VERBATIM, EVERY LINE.** Zero impact from the frontend change. The most expensive knowledge in the repo. |
| §3 the probe | **KEEP the script and the quoted-`$URL` post-mortem.** Retitle "Lane C only, blocks Lane C only." Q1 (`live_url` vs `liveUrl`) → informational; the vendored reference already answers it (`steel-browser-lifecycle.md:63`). Q2 (the `content` envelope) is the one hard blocker and now *more* important. Q3 (`snapshot -u`) → **delete the line.** **ADD Q6: time `browser start` cold** — §2.6's arming budget needs it. **ADD Q7: `curl -I "$LIVE_URL"`** (§2.5). |
| §4.A link extraction | **KEEP every measurement.** Add §5.3's TS twin, the three-flavor href table, and the `rest_v1`-returns-`[]` warning. |
| §4.B Steel client | **KEEP verbatim**, incl. the native-installer paragraph and "time one full hop and write the number down" — now load-bearing for arming, not a soft target. |
| §4.C LLM picker | **KEEP VERBATIM.** The `link_index` warning and the 61–66%-loop citation both stand. Only ownership moves. |
| §4.D display | **DELETE ENTIRELY.** Both obligations re-homed: anchor text → §6.1's `anchor_text` + `AgentLog`; "render every ending" → §4.4's six-row table. |
| §4.E race/CLI/config/README | **AMEND** per §7. `config.py` keeps all four bullets incl. "do not hard-check `STEEL_API_KEY`". `cli.py` **keeps working** as the headless agent-only path — Lane C's regression harness and the "browser died, we still have a demo" insurance — but **delete the stdin daemon thread**. `requirements.txt` **unchanged** (zero new deps). |
| §5 build order `B→A→C→D→E` | **REVERSE.** New: frontend shell + mock feed → renderer + TS wiki → links/wiki Python → picker → steel client → loop + server. The demo is now *showable with a mock agent and no Steel*, and *unshowable with a perfect agent and no UI*. §5's "D doubles as an offline fallback" transfers to `mockFeed`, which is better insurance — it demos the whole game, not one pane. |
| §6 repo tree | Add `web/`, `speedrun/{server,events,console}.py`; delete `speedrun/display.py`, `tests/test_display.py`. |

---

## 9. The three lanes

> **Only touch files your lane owns.** Importing across lanes is expected; *editing* across lanes
> is a chat message, not a commit.

### 9.0 Prologue — 20 min, ONE person. Lane C does not wait.

**Everyone, minute 0, own machine:**
```bash
node --version && npm --version          # need >=18/>=9.  Verified here: v22.23.1 / 10.9.8
python3.11 --version                     # 3.11.15 here. NOT python3 (3.9.6)
curl -s -o /dev/null -w '%{http_code}\n' 'https://en.wikipedia.org/w/api.php?action=parse&page=Cat&prop=text&format=json&origin=*'
curl -s -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org/
curl -s -o /dev/null -w '%{http_code}\n' 'https://fonts.googleapis.com/css2?family=Inter'
```
⚠️ **Run the last three on venue wifi the moment you arrive.** A captive portal intercepting
Wikipedia, npm, or Google Fonts is the one thing that kills the whole demo. If any isn't 200,
tether to a phone.

**Prologue person:**
```bash
cd ~/Desktop/bots-wiki-race
npm create vite@latest web -- --template react-ts
cd web && npm install && npm install -D tailwindcss @tailwindcss/vite
rm src/index.css src/App.css        # the template ships a dark-mode body rule
mkdir -p src/{agent,lib,state,screens,components,styles}
printf 'node_modules\ndist\n' > .gitignore
```
```ts
// web/vite.config.ts — Tailwind v4 is a VITE PLUGIN. No tailwind.config.js. See §3.5.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({ plugins: [react(), tailwindcss()] });
```
Then, same sitting: `src/styles/theme.css` (§3.5 verbatim — **token block FROZEN**), the fonts
`<link>` in `index.html` (§3.4 verbatim), **`src/agent/types.ts` (§6.1 verbatim — this is the
freeze that makes the split work)**, `src/main.tsx` importing `theme.css`, and a 10-line `App.tsx`
(beige page, one lowercase Fraunces h1, one black pill) as CP0's artifact. Commit, push, post
**"scaffold up"**.

### 9.1 Ownership

| File | Owner |
|---|---|
| `speedrun/types.py`, `__init__.py`, `conftest.py`, `requirements.txt`, `.env.example`, `tests/fixtures/*` | **FROZEN** (already on master) |
| `web/{package.json,vite.config.ts,tsconfig*,index.html}`, `src/styles/theme.css`, `src/agent/types.ts` | **FROZEN** (prologue) |
| `web/src/components/{Pill,TopNav,TimerBar,TimerDigits,TitleInput,Card,InlineError,DifficultySegment}.tsx` | **Lane A** |
| `web/src/lib/{wikiApi,pairs}.ts`, `src/state/{gameStore,useClock}.ts` | **Lane A** |
| `web/src/screens/{Setup,Results}.tsx`, `src/App.tsx`, `src/agent/{mockFeed,sseFeed,index}.ts` | **Lane A** |
| `web/src/lib/{links,articleHtml}.ts`, `src/components/ArticleFrame.tsx`, `src/styles/article.css` | **Lane B** |
| `web/src/components/{PlayerPanel,AgentPanel,AgentLog,PathTrail,TargetBadge}.tsx`, `src/screens/Race.tsx` | **Lane B** |
| `speedrun/{links,wiki}.py`, `tests/test_links.py` | **Lane B** ← same head writes both languages of the extractor |
| `speedrun/picker.py`, `tests/test_picker.py` | **Lane B** (moved off C — C is the biggest lane) |
| `speedrun/{steel_client,race,server,events,console,cli,config}.py`, `docs/steel-json-shapes.md`, `README.md` | **Lane C** |
| `speedrun/display.py`, `tests/test_display.py`, `tests/test_wiki.py` | **DELETED — do not create** |

**The one A↔B seam:** `Race.tsx` imports `useGame()` and `<TimerBar>` from Lane A and calls one
action. **Lane A must push a working `gameStore` stub + `wikiApi.fetchArticle` by CP1 or Lane B is
blocked — that's CP1's hard gate.**

### 9.2 Order of work

**Lane A — Shell, Flow & Referee (~7.4h):** `Pill` → `wikiApi` + `pairs` → **`gameStore` STUB
FIRST (20 min, push it — Lane B is blocked)** then the real reducer → `useClock` → `TimerDigits`
(eyeball the §3.3 jitter fix immediately) → **`mockFeed` before the Setup screen** → `TopNav` →
`TitleInput` + `DifficultySegment` → `Setup` → `App` → `Results` (all six outcomes) → `sseFeed`.

**Lane B — Wikipedia, Renderer & Picker (~7.9h):** `links.ts` **first** → `articleHtml.ts` →
`ArticleFrame` → **`article.css`: the visual make-or-break, TIME-BOX 1.5h HARD** (order: the §5.3
hide list and nothing else, then type scale, then `table/.infobox { display:block; overflow-x:auto }`
and `img { max-width:100% }` — those two are what stop a 112-table article blowing out the panel)
→ `PathTrail`/`TargetBadge`/`AgentLog` → `PlayerPanel`/`AgentPanel` → `Race.tsx` → `links.py` +
`test_links.py` (**fixture test red first**) → `wiki.py` → `picker.py`.

**Lane C — Agent & Bridge (~7.1h):** **minute 0, before the prologue lands:**
`curl -fsS https://setup.steel.dev | sh` (**not** npm), `steel login`, `steel doctor --preflight`,
then `PLAN.md` §3's probe **with `$URL` quoted** plus new Q6/Q7 — **time-box 45 min; if auth
fights you, move on and come back** → `steel_client.py` (4 functions, `timeout=` on every
`subprocess.run`, errors include **stdout** not stderr) → `config.py` → `events.py` → `server.py`
→ `race.py` → `console.py` + `cli.py` → `README.md` (last; reassignable at CP4 only).

### 9.3 Rebalance levers, pull in this order
1. **At CP2**, if `article.css` blew its box: Lane A takes `AgentLog` + `TargetBadge` + `PathTrail`
   (1.0h, no renderer knowledge), and `picker.py` goes to whoever is freest.
2. **At CP2**, if the probe is still fighting: Lane C ships `--page-source=http` and moves on. The
   loop, extractor and LLM are unchanged; the demo drops the Steel *claim*, not the race.
3. **At CP3**, if the live feed isn't up by T+7:15: **stop.** Demo on `mockFeed` and show the Python
   agent in a terminal alongside.
4. **At CP4**, `README.md` to whoever is idle. **Never earlier.**

---

## 10. Checkpoints and acceptance

Assumes a 10-hour window, T+0 = GO.

| CP | Time | Artifact | Hard gate |
|---|---|---|---|
| **CP0** | T+0:20 | `npm run dev` → beige gradient, lowercase Fraunces title, one black pill. `theme.css` + `types.ts` pushed. | Lanes A and B unblocked; Lane C already 20 min into Steel install |
| **CP1** | T+1:45 | Setup renders; **`ArticleFrame` renders real `Cat` inside a green card on a light well and clicks log the title**; Lane A's `gameStore` stub + `wikiApi` pushed; `test_links.py` fixture test **green**; timer digits eyeballed at 92px | **"Does 580 KB of `mw-parser-output` look good on a sage card?" gets answered at hour two, not hour eight.** If it looks bad you still have 8 hours. |
| **CP2** | T+4:15 | **THE SHIPPABLE DEMO.** Setup → Race → Results end to end **on `mockFeed`**, with difficulty, target highlight, both trails, shared timer, win detection both directions. Python: `links.py` green, one real Steel hop **timed and written down**. | **Screenshot it. Tag the commit.** From here you always have a demo. |
| **CP3** | T+6:45 | Two terminals; browser at `?agent=real` showing real hops and the live view | **If it isn't working by T+7:15, stop.** Don't spend hour 8 on a transport. |
| **CP4** | T+8:45 **FREEZE** | Three full races rehearsed on the actual machine, at the actual resolution, by the person who'll drive | No new features. Polish to T+9:30, then hands off keyboards. |

**If the window is 6 hours:** drop CP3, ship CP2 on `mockFeed`, show the Python agent in a terminal
alongside as proof it exists. **That's a good demo, not a compromised one** — the UI is identical
either way, which is exactly why §6's mock-first decision is the one that matters.

### Acceptance runs

`PLAN.md` §4.E's three commands are **demoted, not deleted** — they're Lane C's headless regression
suite, and run 3 is still the redirect regression that would have failed on stage under v1.

```bash
python3.11 -m pytest tests/test_links.py    # len(extract_candidates(fixture)) > 200
npm --prefix web run test                   # extractCandidates(fixture).size > 200, SAME rule
python3.11 -m speedrun.cli --start "Snakes" --target "WWII"   # then: steel browser sessions -> empty
```

| # | Run | Must observe |
|---|---|---|
| R1 | `npm run dev`, **no API keys set at all** | Full Setup → Race → Results on `mockFeed`. *Proves the app is demoable with zero backend — the stage fallback.* |
| R2 | `?agent=real`, human clicks to the target | Timer stops the instant the player's canonical title matches; both panels freeze; `POST /stop` fires; **`steel browser sessions` is empty**. *Catches the leaked-session-on-human-win path, which no v2 code had.* |
| R3 | `?agent=real`, human does nothing | "Agent won!", hop count, and the agent's path **with the anchor texts it clicked**. |
| R4 | Type `Snakes` → `WWII` at Setup | Resolves to *Snake* / *World War II* **before the clock starts**; badge reads "Reach: World War II"; win fires on canonical title for either racer. *The v1-killer, now in the browser.* |
| R5 | Player wins while the agent is mid-route, ~400 ms from landing (use the Photo finish button in `/race-preview.html`, which computes it from mockFeed's `hops x 2450ms` schedule) | "You won!", **exactly one transition, NO REVERSAL**, and the agent stopped mid-route without claiming a win. ⚠️ **AMENDED 2026-09-12 — the original wording asked for a "Photo finish — won by 0.4s" caption, which this architecture cannot produce and should not.** `tryAnnounce()` tears the feed down the instant someone wins, so the agent's arrival 400 ms later is never delivered and `marginMs` stays null. That is correct: with a real agent we `POST /stop` mid-hop, the agent never lands, and a margin against an arrival that never happened would be fiction. §2.6 already decided ties are not a code path and the race stops on first finish — this run originally contradicted that. `Results.tsx`'s `marginMs < 1000` caption stays as defensive code for the genuinely-simultaneous case; it is not stageable, so do not try to test it. **Verified passing 2026-09-12** on a 3-hop pair: agent landing at 7,350 ms, player winning at 6,950 ms, no reversal. |
| R6 | `?agent=real --max-hops 3` on a `hard` pair | Agent panel: calm in-palette "gave up after 3 hops"; **the human's race continues**; Results is one-sided and doesn't crash. *The state the spec's machine lacks.* |
| R7 | Kill `speedrun.server` mid-race | "Agent disconnected"; the human's timer keeps running; no unhandled rejection. |
| R8 | Prewarm, sit on Setup 6 minutes, then Start | Race still starts; `ready` re-fires; session recreated (trap 4). *The "second demo of the evening" test.* |
| R9 | Each difficulty tier once | Easy: agent doesn't take a visible one-hop win. Hard: Sonnet path produces a real `choose_link`, **not** `was_fallback` on every hop (§5.5). |

One grep gate, plus two assertions that replace grep gates I originally got wrong:

```bash
# A leaked key path is genuinely grep-shaped. Run it before every demo.
grep -rEn 'sk-ant|STEEL_API_KEY|VITE_ANTHROPIC' web/src/ web/dist/ && echo "FAIL: key path in frontend"
```

⚠️ **Two grep gates in the first draft of this section were wrong, and Lane B hit both.**
`grep 'rest_v1/page/html' web/src/` fires on the *comment in `links.ts` explaining never to
use it*, and `grep 'hatnote' web/src/styles/` fires on the rule that *styles* hatnotes as
editorial asides — styling is not hiding. Both cried wolf on correct code, which is how a
gate gets ignored and then misses the real thing. They are replaced by assertions that
target the actual mistake, and both already pass:

| Was a grep for | Is now |
|---|---|
| `rest_v1/page/html` | `titleFromHref("./Renaissance") === null` in `links.test.ts`, and `test_rejects_rest_v1_relative_hrefs` in `test_links.py`. The defect is *accepting the `./Title` href form*, not mentioning the endpoint. |
| `hatnote` in styles | `expect(EXCLUDE_SELECTOR).not.toContain("hatnote")` and `.not.toContain("infobox")` in `links.test.ts`. The defect is *excluding a legal move*, not styling one. |

Both languages also assert the parity that makes any of this meaningful: the TS and Python
extractors return identical title lists in identical order against the committed fixture.

---

## 11. Your six answers, as built

| # | You said | Where it lives |
|---|---|---|
| 1 | *"what screenshot"* | §3.1 — the spec's own opening line says "the reference screenshot attached"; there was no image at first, you sent it later, and it settled the composition. **Your tokens are the design authority, not dialed.gg.** |
| 2 | Steel live view **shown and prominent**, no toggle | §2.5 (verified it frames, `?interactive=false`), §4.3 (968×544 in the stacked right column). Trade-off stated: panel parity is structural, not visual. |
| 3 | **Easy / medium / hard** | §5.5 (two honest levers, no handicap), §5.4 (20 measured pairs). |
| 4 | **Yes**, highlight the player's target link | §4.3, and the honesty copy: the agent has this free via `find_target`, so it restores symmetry rather than granting an advantage. |
| 5 | Mid-race reload — **no** | §2.7. Deleted the recovery path; kept replay-on-connect, which is load-bearing for the *initial* connect. |
| 6 | Presenter **is** the player | §5.5 (Easy exists so a narrating human can win), §4.3 (keyboard hints off the HUD), and R1 (`mockFeed` gives a hands-free race to talk over). |

## 12. Still open

1. **The Results screen's giant-number treatment** is the last visual unknown — the screenshot is
   the intro state and has no timer. One CSS variable (`--size-result`); send that screen if you
   have it, before CP2.
2. **Does `hard` ship on Sonnet or Haiku?** Costs 0.5h to fix the thinking config (§5.5). If you'd
   rather spend that half-hour elsewhere, `hard` runs Haiku on longer pairs and is still hard.
3. **Lane assignment** — who takes A, B, C. Lane C should be whoever's most comfortable with
   subprocess plumbing; it's the critical path and owns the Steel install.
