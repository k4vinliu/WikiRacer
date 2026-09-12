# Lane A — verbatim snippets

Copy these. Do not restyle tokens. Do not rename event fields.

## Frozen `theme.css` token block (`FRONTEND.md` §3.5)

Not yours to change. Import it. Use the utilities.

```css
@theme {
  --color-bg-page:            #F3EBE0;
  --color-bg-page-alt:        #EFE0D2;
  --color-card-green:         #33443A;
  --color-card-green-soft:    #445A4E;
  --color-surface-grey:       #E7E4DD;
  --color-surface-grey-dark:  #D8D4CA;
  --color-surface-well:       #FAF6EF;
  --color-text-on-dark:       #F3F1EA;
  --color-text-on-dark-muted: #C5CBC3;
  --color-text-on-light:      #232823;
  --color-text-on-light-muted:#585E56;
  --color-text-on-light-subtle:#6E756C; /* ≥18.66px ONLY */
  --color-accent-black:       #171717;
  --color-divider:            #DAD3C6;
  --color-error:              #934535;
  --color-error-on-dark:      #E0A292;
  --font-display: "Fraunces", ui-serif, Georgia, serif;
  --font-body:    "Inter", ui-sans-serif, system-ui, sans-serif;
  --radius-hero: 32px;
  --radius-card: 24px;
  --radius-pill: 999px;
}
:root { --size-result: min(150px, 30vw); }
```

`--card-green-soft` vs `--card-green` is contrast **1.39** — a hover that only swaps those two is invisible. Pair with shadow or divider.

## Frozen `AgentEvent` (`FRONTEND.md` §6.1)

```ts
export type Difficulty = "easy" | "medium" | "hard";
export type Winner = "bot" | "human" | "none";
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
  subscribe(on: (e: AgentEvent) => void): () => void;
}
```

## `wikiApi.ts` URLs and resolve (`FRONTEND.md` §5.1)

```ts
const API = "https://en.wikipedia.org/w/api.php";
const enc = (t: string) => encodeURIComponent(t.replace(/ /g, "_"));

export const parseUrl = (t: string) =>
  `${API}?action=parse&page=${enc(t)}&prop=text&redirects=1&disableeditsection=true` +
  `&format=json&formatversion=2&origin=*`;

export const canonUrl = (ts: string[]) =>
  `${API}?action=query&titles=${ts.map(enc).join("|")}&redirects=1` +
  `&format=json&formatversion=2&origin=*`;

export const searchUrl = (q: string) =>
  `${API}?action=opensearch&search=${encodeURIComponent(q)}&limit=8&namespace=0` +
  `&format=json&origin=*`;

const key = (t: string) => String(t).replace(/ /g, "_");
const resolve = (t: string, m: Map<string, string>) => {
  const x = m.get(key(t)) ?? m.get(t) ?? t;
  return m.get(x) ?? x;
};
```

`fetchArticle` returns `{ title: parse.title, html: parse.text }` — `parse.title` is already redirect-resolved. `page=Snakes` → `"Snake"`; missing page → `error.code: "missingtitle"`.

## `TimerDigits` (`FRONTEND.md` §3.3)

```tsx
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

Fonts (prologue owns `index.html`; if you must add them, this exact URL):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,400..600,50,0;1,9..144,400..600,50,1&family=Inter:wght@400;500;600&display=swap">
```

Flavor captions only: `ital 1` + `WONK 1`. Never on the timer.

## `PAIRS` (`FRONTEND.md` §5.4)

`hops: 2` is exact. `hops: 3` means proven not 1 and not 2 (`atLeast: true`). No 1-hop pair.

```ts
export type Pair = { start: string; target: string; hops: 2 | 3; atLeast?: true; fanout: number };

export const PAIRS: Record<Difficulty, Pair[]> = {
  easy: [
    { start: "Cat",      target: "Napoleon",            hops: 2, fanout: 472 },
    { start: "Chess",    target: "Antarctica",          hops: 2, fanout: 537 },
    { start: "Honey",    target: "Saturn",              hops: 2, fanout: 419 },
    { start: "Tea",      target: "Basketball",          hops: 2, fanout: 415 },
    { start: "Banana",   target: "Jazz",                hops: 2, fanout: 414 },
    { start: "Guitar",   target: "Albert Einstein",     hops: 2, fanout: 349 },
    { start: "Bicycle",  target: "William Shakespeare", hops: 2, fanout: 322 },
  ],
  medium: [
    { start: "Sushi",     target: "Volcano",       hops: 2, fanout: 299 },
    { start: "Umbrella",  target: "Tsunami",       hops: 2, fanout: 289 },
    { start: "Pizza",     target: "Mars",          hops: 2, fanout: 204 },
    { start: "Waffle",    target: "Tornado",       hops: 2, fanout: 125 },
    { start: "Violin",    target: "Glacier",       hops: 3, atLeast: true, fanout: 350 },
    { start: "Coffee",    target: "Mount Everest", hops: 3, atLeast: true, fanout: 312 },
    { start: "Chocolate", target: "Samurai",       hops: 3, atLeast: true, fanout: 312 },
  ],
  hard: [
    { start: "Origami",    target: "Submarine",  hops: 3, atLeast: true, fanout: 144 },
    { start: "Pencil",     target: "Kangaroo",   hops: 3, atLeast: true, fanout: 185 },
    { start: "Lighthouse", target: "Dinosaur",   hops: 3, atLeast: true, fanout: 215 },
    { start: "Soap",       target: "Jupiter",    hops: 3, atLeast: true, fanout: 224 },
    { start: "Bread",      target: "Black hole", hops: 3, atLeast: true, fanout: 240 },
    { start: "Penguin",    target: "Sahara",     hops: 3, atLeast: true, fanout: 256 },
  ],
};

export const REDIRECT_FIXTURES = [
  { typed: "Snakes", canonical: "Snake" },
  { typed: "WWII",   canonical: "World War II" },
  { typed: "Obama",  canonical: "Barack Obama" },
];
```

## Results headlines (`FRONTEND.md` §4.4)

| `reason` | Headline |
|---|---|
| `won` + `winner:"human"` | **You won!** (+ photo-finish caption if margin < 1.0s) |
| `won` + `winner:"bot"` | **Agent won!** |
| `hop_limit_reached` | **The agent gave up** (human may still be racing — Results is one-sided if they finish later) |
| `dead_end` | **The agent hit a dead end** |
| `human_finished_first` | **You won!** |
| `error` | **Race ended early** (host-readable message, never a stack trace) |

## Clock (`FRONTEND.md` §2.6)

```ts
export const elapsedMs = (t0: number) => performance.now() - t0;
```

```
ready --[Start Race]--> arming --(both ready, ≤20s)--> 3..2..1 --> GO --> racing
```

`POST /race/{id}/go` is the gun when `?agent=real`. On `mockFeed`, you still two-phase: wait until the start article is painted and the mock emits `ready`.
