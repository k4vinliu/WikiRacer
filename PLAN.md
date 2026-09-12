# Wikipedia Speedrun — Master Plan (Human vs. AI Bot Wiki Race)

**Status:** Design approved, implementation not started.
**Purpose of this document:** This is written so any team member — or any AI coding agent working on their behalf — can pick up ONE section below and build it independently, without needing to read the other sections first, and without needing the rest of the codebase to exist yet. All cross-module dependencies are pinned down as explicit interfaces/contracts in Section 2. If you're an agent picking up a work package, read Section 1 (context) and Section 2 (contracts) in full, then only your assigned Section 4.x package.

---

## 1. Project Context

We're building a live hackathon demo: a **human and an AI bot race on Wikipedia**. Both start on the same article and must reach the same target article, moving only by clicking links that appear in the article body — the classic "wiki race" game. It runs live on a projector at a hackathon.

**Locked decisions (do not revisit / re-litigate these):**
- It's human vs. bot, not bot vs. bot.
- The human races on their own real laptop/browser. That is **out of scope for code** — it's a physical/projector setup concern only. The human's finish is called manually by whoever is hosting the race.
- The bot is driven by **Steel** — a browser-automation CLI (`steel`) already installed and authenticated on the team's machines (cloud-hosted headless browser sessions, controlled via CLI commands). See Section 2.3 for the exact commands available.
- The bot's link-picking decision at each step is made by an LLM (**Claude**, via the Anthropic API) reasoning over the current article, the target, and the list of candidate links.
- The host manually types in the start and target article for each race — no randomization logic needed.
- The bot **auto-detects its own win** by comparing its current page URL to the target after every hop. There is a hop limit (default 25) so a live demo never hangs forever.
- **Projector layout** (3 panes, side by side): human's own browser | Steel's live-view of the bot's browser | a terminal showing the bot's live-updating reasoning log (one line per hop: "On X, target Y — clicking Z because ...").
- **Language: Python.** The bot orchestration shells out to the `steel` CLI via `subprocess` (not a rewritten API client) — this was already validated working in exploratory testing this session (`steel browser start/navigate/content/click/stop` all return clean JSON via `--json`).
- **This is a hackathon demo tool, not a production service.** Keep everything as simple as it can be while still working reliably live on stage. No web backend, no database, no auth beyond the two required API keys.

**Required environment/credentials** (every team member needs both):
- `STEEL_API_KEY` — Steel account API key (from steel.dev dashboard, or `steel login`)
- `ANTHROPIC_API_KEY` — Anthropic API key

**Repo setup note:** the project directory is currently empty (not yet a git repo). Whoever picks this plan up first should `git init`, commit this `PLAN.md`, and push to GitHub so the team can branch off it.

---

## 2. Shared Contracts (read this before touching any package — this is what makes parallel work possible)

Every package below is built against these interfaces. If you're implementing Package A, you don't need Package B to exist — you just need to produce something that matches these shapes, and you can write your own throwaway test data that matches them too.

### 2.1 Data types (conceptually — implement as Python `dataclass`es, one shared `speedrun/types.py` module)

```python
@dataclass
class Candidate:
    index: int        # position in the candidate list shown to the LLM (0-based)
    text: str          # visible anchor text shown to the LLM, e.g. "Renaissance"
    title: str         # canonical Wikipedia article title, e.g. "Renaissance"
    href: str          # original href as found in the HTML, e.g. "/wiki/Renaissance"

@dataclass
class PickResult:
    candidate: Candidate
    reason: str        # one short sentence, shown in the reasoning log
    was_fallback: bool # True if the LLM call failed/was invalid and we fell back deterministically

@dataclass
class HopEvent:
    hop: int
    current_title: str
    picked: PickResult

@dataclass
class RaceResult:
    won: bool
    hops: int | None = None
    reason: str | None = None   # e.g. "hop_limit_reached", "bot_stuck"
    error: str | None = None

@dataclass
class SessionHandle:
    name: str          # the --session name we chose, e.g. "speedrun-1770000000"
    live_url: str       # projector URL for Steel's live view of this session
```

### 2.2 Function-level interfaces each package must implement

```python
# speedrun/links.py  (Package A)
def extract_candidates(html: str, max_candidates: int = 300) -> list[Candidate]: ...

# speedrun/wiki.py  (Package A)
def title_from_url(url_or_title: str) -> str: ...
def titles_match(a: str, b: str) -> bool: ...

# speedrun/picker.py  (Package C)
def choose_link(
    model: str,
    current_title: str,
    target_title: str,
    visited: list[str],
    candidates: list[Candidate],
    hop: int,
    max_hops: int,
) -> PickResult: ...

# speedrun/steel_client.py  (Package B)
def start_session(inactivity_timeout_ms: int = 0) -> SessionHandle: ...
def navigate(session_name: str, url: str) -> None: ...
def wait_load(session_name: str, timeout_ms: int = 30000) -> None: ...  # swallow timeout, log + continue
def get_url(session_name: str) -> str: ...
def content(session_name: str) -> str: ...  # raw page HTML
def resolve_click_ref(session_name: str, candidate: Candidate) -> str: ...  # returns an @eN ref or CSS selector string
def click(session_name: str, ref: str) -> None: ...
def stop_session(session_name: str) -> None: ...

# speedrun/display.py  (Package D)
def print_live_url(live_url: str) -> None: ...
def log_hop(event: HopEvent) -> None: ...
def log_stuck(hop: int, candidate: Candidate, retry_count: int) -> None: ...
def announce_winner(hops: int) -> None: ...
def announce_stuck() -> None: ...
def announce_timeout(max_hops: int) -> None: ...
def log_error(exc: Exception) -> None: ...

# speedrun/race.py + cli.py  (Package E — integration)
def run_race(start_url: str, target_url: str, model: str, max_hops: int = 25) -> RaceResult: ...
```

**Rule for every package:** if you need to change one of these signatures, that's a cross-team decision — post it in the team chat/PR description, don't just silently change it, since other packages are being built against the signature as written.

### 2.3 Steel CLI commands you're allowed to rely on (confirmed to exist; exact JSON field names should be confirmed by Package B via the probe script in Section 3)

```
steel browser start --session <name> --inactivity-timeout <ms> --json
steel browser navigate <url> --session <name> --wait-until networkidle
steel browser get url --session <name> --json
steel browser get attr @eN href --session <name> --json
steel browser content --session <name> --json
steel browser snapshot -i -s "#mw-content-text" --session <name> --json
steel browser click <@eN-ref-or-css-selector> --session <name>
steel browser wait --load networkidle --session <name> --timeout <ms>
steel browser stop --session <name>
```
Full reference: `.claude/skills/steel-browser/references/steel-browser-commands.md` and `steel-browser-lifecycle.md` in this repo (installed via `npx skills add steel-dev/skills --skill steel-browser`).

### 2.4 Claude tool-call contract (Package C owns the implementation, but this shape is fixed)

```python
CHOOSE_LINK_TOOL = {
    "name": "choose_link",
    "description": "Pick exactly one candidate link to click next in the Wikipedia speedrun.",
    "input_schema": {
        "type": "object",
        "properties": {
            "link_index": {"type": "integer", "description": "Index of the chosen link from the numbered candidate list."},
            "reason": {"type": "string", "description": "One short sentence (<=20 words) explaining the choice."}
        },
        "required": ["link_index", "reason"],
        "additionalProperties": False
    }
}
# tool_choice={"type": "tool", "name": "choose_link"} — always force the tool call, no freeform text turn
# default model: "claude-haiku-4-5-20251001" (fast, cheap, low per-hop latency for a live demo)
# swappable via --model flag, e.g. "claude-sonnet-5" for stronger picks at higher latency
```

---

## 3. First Step (whoever starts first should do this, ~10 minutes, unblocks Package B)

Run this probe once to confirm Steel's actual JSON field names before Package B writes its parser (do NOT skip — earlier exploration only confirmed the general JSON shape, not the literal field names for `get url`/`content`/`snapshot`):
```bash
export STEEL_API_KEY=...
steel browser start --session probe --inactivity-timeout 0 --json
steel browser navigate https://en.wikipedia.org/wiki/Python_(programming_language) --session probe --json
steel browser get url --session probe --json
steel browser content --session probe --json
steel browser snapshot -i -s "#mw-content-text" --session probe --json
steel browser stop --session probe --json
```
Paste the actual JSON output into a `docs/steel-json-shapes.md` file in the repo so Package B (and anyone debugging) has ground truth instead of guessing.

---

## 4. Work Packages (parallelizable)

Packages A, B, C, D have **no dependency on each other's code** — only on the shared contracts in Section 2. They can be built simultaneously by four different people/agents. Package E (integration) is the only one that assembles the others, so it's either done last, or scaffolded in parallel against mock/stub versions of A–D and wired up for real once they land.

### 4.A — Pure Logic: Link Extraction & Wiki Title Matching
**Owns:** `speedrun/links.py`, `speedrun/wiki.py`, `tests/test_links.py`, `tests/test_wiki.py`
**Dependencies:** none (no Steel account or Anthropic key needed — fully offline)
**Can start immediately.**

Build:
- `links.extract_candidates(html, max_candidates=300) -> list[Candidate]`:
  1. Parse with BeautifulSoup, scope to `#mw-content-text` (fall back to whole doc if that selector is missing, so it degrades instead of crashing).
  2. Remove subtrees matching `.reflist, .reference, ol.references, .navbox, .mw-editsection, .hatnote` before collecting `<a>` tags (strips citations/chrome, keeps legit moves like "See also" and infobox links).
  3. Keep only `href` starting with `/wiki/`. Skip these namespace prefixes after `/wiki/`: `File:`, `Category:`, `Special:`, `Help:`, `Portal:`, `Template:`, `Template_talk:`, `Module:`, `Draft:`, `User:`, `User_talk:`, `Wikipedia:`, `Wikipedia_talk:`, `MediaWiki:`, `TimedText:`, `Book:`, `Talk:` (must be an exact prefix match on the segment before the first `:` inside the title, not a "contains a colon" check — legitimate titles like *Batman: The Animated Series* must survive).
  4. Skip `href`s containing `#cite_note` or `#cite_ref`.
  5. URL-decode the title portion, replace `_` with space → `Candidate.title`. Anchor's visible text (`a.get_text(strip=True)`, falling back to `title` if empty) → `Candidate.text`.
  6. Dedupe by `title`, keeping first occurrence (document order). Truncate to `max_candidates`, assign `index` 0..N-1 in the final order.
- `wiki.title_from_url(url_or_title)`: if input contains `/wiki/`, take the segment after it; URL-decode, replace `_` with space, strip any `#fragment`. If it's already a bare title, just clean it the same way (strip whitespace).
- `wiki.titles_match(a, b)`: run both through the same normalization and compare case-insensitively.

Tests (no network, use inline HTML fixture strings):
- A fixture `#mw-content-text` div containing: 2-3 legit `/wiki/Foo` links, a duplicate of one, a `/wiki/File:X.jpg` link, a `/wiki/Category:Y` link, a `<sup class="reference">` citation anchor, and a `<div class="reflist">...</div>` block → assert `extract_candidates` returns exactly the expected filtered/deduped/ordered list.
- A fixture with more than `max_candidates` links → assert truncation.
- `title_from_url` on a bare title, a percent-encoded/underscored URL, and a URL with `#fragment`.
- `titles_match` across case differences, underscore-vs-space, and a clear non-match.

**Acceptance criteria:** `pytest tests/test_links.py tests/test_wiki.py` passes, 100% offline, no env vars needed.

---

### 4.B — Steel Browser Client
**Owns:** `speedrun/steel_client.py`
**Dependencies:** `STEEL_API_KEY`, the `steel` CLI installed (`npm install -g @steel-dev/cli`), and the probe output from Section 3.
**Can start immediately** once the probe (Section 3) has run.

Build a thin `subprocess`-based wrapper implementing every function signature in Section 2.2. Guidelines:
- Every call passes `--json` and parses stdout with `json.loads`; raise a clear exception (include the raw stderr) on non-zero exit code rather than silently returning `None`.
- `start_session`: run `steel browser start --session <generated-name> --inactivity-timeout <ms> --json`. Generate the session name yourself, e.g. `f"speedrun-{int(time.time())}"`. Parse `live_url` (or whatever the probe confirms the actual field is called) and `id`/`name` into a `SessionHandle`.
- `wait_load`: call `steel browser wait --load networkidle --session <name> --timeout <ms>`; if it exits non-zero due to timeout specifically, log a warning and return normally rather than raising — a slow-loading page shouldn't crash the race.
- `resolve_click_ref(session_name, candidate)`: take one scoped snapshot (`steel browser snapshot -i -s "#mw-content-text" --session <name> --json`), search interactive elements for one whose href/url field matches `candidate.href` exactly. If the snapshot schema doesn't expose href (confirm via probe), fall back to matching trimmed visible text. If neither matches, fall back to returning the CSS selector string `f"#mw-content-text a[href='{candidate.href}']"` (Steel's `click` command accepts either an `@eN` ref or a raw selector).
- `stop_session`: must not raise if the session is already gone (e.g., idempotent — treat "session not found" as success, since cleanup code will call this in error paths too).

**Acceptance criteria:** a manual smoke script (not necessarily pytest, since this needs a live Steel session) that does: start → navigate to a real Wikipedia page → get_url → content → resolve_click_ref on a real link found in that content → click → get_url again (confirming it changed) → stop. Confirm via `steel browser sessions` that nothing is left running afterward.

---

### 4.C — LLM Link Picker
**Owns:** `speedrun/picker.py`, `tests/test_picker.py`
**Dependencies:** `ANTHROPIC_API_KEY` for real calls; tests themselves must NOT hit the network (mock the Anthropic client).
**Can start immediately.**

Build `choose_link(...)` per Section 2.2, using the tool contract in Section 2.4:
- **System prompt** (fixed, roughly): "You are playing a Wikipedia speedrun (wiki race). You start on one article and must reach a target article by clicking only links that appear in the article body. On each turn you'll see the current article, the target article, the articles already visited this race, and a numbered list of candidate links from the current article. Pick exactly one link most likely to lead toward the target in the fewest hops, using your general knowledge of how topics connect on Wikipedia. Avoid re-visiting an already-visited article unless it's clearly the best option. Call `choose_link` with your pick and a single short reason."
- **User prompt per hop**: current article, target article, visited list so far (or "(none yet)"), `hop`/`max_hops`, and the numbered `text -> title` candidate list.
- Call `client.messages.create(...)` with `tool_choice` forcing `choose_link`, `max_tokens=300`.
- **Validation** (pull this into a pure `parse_choice(response, candidates, visited)` helper so it's unit-testable without mocking the whole `choose_link` call): require `stop_reason == "tool_use"` with a `choose_link` block present, and `0 <= link_index < len(candidates)`.
- **Fallback** — triggered by: API exception/timeout, wrong `stop_reason`, missing/out-of-range `link_index`, or an empty `candidates` list. Fallback action: deterministically pick the first candidate whose title differs from the most recent visited title (avoid trivial bounce-back), and return `PickResult(was_fallback=True, reason="[fallback] ...")`.

Tests (mock `client.messages.create` to return canned response objects, no network):
- Valid tool_use response with in-range index → accepted, `was_fallback=False`.
- Out-of-range `link_index` → fallback triggered.
- Non-`tool_use` stop reason (e.g. simulate a refusal) → fallback triggered.
- Empty `candidates` list → fallback triggered without even calling the API (short-circuit).

**Acceptance criteria:** `pytest tests/test_picker.py` passes with zero network calls (assert via mock call count / no real API key needed to run tests).

---

### 4.D — Live Reasoning Log Display
**Owns:** `speedrun/display.py`
**Dependencies:** `rich` library only. No Steel or Anthropic dependency at all — can be built and demoed standalone by feeding it fake `HopEvent`s in a `__main__` block.
**Can start immediately.**

Build all functions in Section 2.2 using `rich.live.Live` + `rich.table.Table`:
- One persistent `Table` with columns: Hop, Current Article, Chosen Link, Reason (prefix `[fallback]` visually, e.g. dim/yellow style, when `was_fallback=True`).
- `log_hop` appends a row and calls `live.update(table)`.
- `print_live_url` prints the projector URL prominently (e.g. a `rich.panel.Panel` in a bright color) at the start of the race so the host can immediately copy it into a browser tab.
- `announce_winner` / `announce_stuck` / `announce_timeout` should be visually unmissable from a distance (large colored banner text — this is being read off a projector).
- Must **degrade to plain sequential `print()` calls** if `sys.stdout.isatty()` is False (e.g., output piped to a log file) — don't let a live demo depend on TTY detection working correctly; test both paths.

**Acceptance criteria:** a `python -m speedrun.display` demo mode (or similar) that fabricates 5-6 fake hops including one fallback and a final winner announcement, runs with no env vars/network at all, and looks good on screen.

---

### 4.E — Race Orchestration, CLI, Config, README (Integration)
**Owns:** `speedrun/race.py`, `speedrun/cli.py`, `speedrun/config.py`, `requirements.txt`, `README.md`
**Dependencies:** the interfaces from Packages A–D (can be stubbed/mocked to start scaffolding early, then wired to the real implementations as they land — this package doesn't have to wait if whoever owns it wants to build against fakes first).

Build:
- `config.py`: validate `STEEL_API_KEY` and `ANTHROPIC_API_KEY` are set at startup; raise a clear, host-friendly error message (not a stack trace) if either is missing. Hold defaults: `DEFAULT_MODEL = "claude-haiku-4-5-20251001"`, `DEFAULT_MAX_HOPS = 25`.
- `race.run_race(start_url, target_url, model, max_hops=25) -> RaceResult`: implements the loop exactly as specified in Section 2.2's signature, calling into `steel_client`, `links`, `wiki`, `picker`, `display`. Structure:
  1. Start session (disable inactivity timeout — a live demo has unpredictable pauses for crowd commentary).
  2. Print live URL immediately.
  3. Navigate to start.
  4. Loop up to `max_hops`: wait for load → read current URL/title → check win → extract candidates from content → ask picker → log the hop → resolve + click → wait for load → read new URL → check win again → track "stuck" (URL unchanged after click) with a retry cap of 5 across the whole race before declaring a clean loss.
  5. `try/finally`: **always** call `stop_session`, whether the race won, hit the hop limit, got stuck, or raised an exception — this is a hard requirement, a live demo must never leak a running cloud session.
- `cli.py`: `argparse` entrypoint — `python -m speedrun.cli --start "<title-or-url>" --target "<title-or-url>" [--model ...] [--max-hops N]`. Wrap the call to `run_race` so a `KeyboardInterrupt` prints "stopping Steel session..." before exiting cleanly (cleanup already guaranteed by `race.py`'s `finally`, this is just a friendlier message for the host).
- `requirements.txt`: `anthropic>=0.40`, `beautifulsoup4>=4.12`, `rich>=13.7` (+ `pytest` as a dev dependency).
- `README.md` must cover: prerequisites (Python version, `steel` CLI install + `steel login` or `STEEL_API_KEY`, `ANTHROPIC_API_KEY`), install steps (`pip install -r requirements.txt`), exact run command example, the 3-pane projector layout description, and a troubleshooting note ("if the bot seems to hang, check `steel browser sessions` for a stuck session and `steel browser stop --all`").

**Acceptance criteria (end-to-end manual dry run, the primary verification for this whole project):**
```bash
python -m speedrun.cli --start "Python (programming language)" --target "Snake" --max-hops 25
```
Confirm: live-view URL prints and works, hop-by-hop reasoning appears in the terminal, the race either reaches "Snake" or cleanly reports the hop limit, and `steel browser sessions` shows nothing lingering afterward. Repeat once more, hitting Ctrl+C mid-race, and re-confirm no lingering session.

---

## 5. Integration Order (if not doing true parallel start)

If the team can't truly parallelize (e.g. only 1-2 people), build in this order for fastest path to a working demo: **A → C → B → D → E**. Rationale: A and C need no live credentials and can be fully tested offline first; B needs a Steel account and is the riskiest/least-known part (do it early to surface surprises); D is low-risk and fast; E is trivial once A-D exist since it's just wiring per the exact interfaces already pinned down in Section 2.

## 6. Repo Structure (final)

```
.
├── PLAN.md
├── README.md
├── requirements.txt
├── .env.example              # STEEL_API_KEY=..., ANTHROPIC_API_KEY=...
├── docs/
│   └── steel-json-shapes.md  # output of the Section 3 probe
├── speedrun/
│   ├── __init__.py
│   ├── types.py               # shared dataclasses (Section 2.1)
│   ├── config.py               # Package E
│   ├── steel_client.py         # Package B
│   ├── wiki.py                 # Package A
│   ├── links.py                # Package A
│   ├── picker.py                # Package C
│   ├── display.py               # Package D
│   ├── race.py                  # Package E
│   └── cli.py                   # Package E
└── tests/
    ├── test_wiki.py             # Package A
    ├── test_links.py            # Package A
    └── test_picker.py           # Package C
```
