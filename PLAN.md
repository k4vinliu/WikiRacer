# Wikipedia Speedrun — Master Plan (Human vs. AI Bot Wiki Race)

**Status:** **Contracts v2 — amended 2026-09-12 after review.** Implementation not started.
**Read this first:** Section 3 (the probe) is now a **hard gate that runs before any package starts**, not a parallel task. Section 2 was amended in six places; the amendment log is at the top of Section 2. If you read v1, re-read Section 2.
**Purpose of this document:** This is written so any team member — or any AI coding agent working on their behalf — can pick up ONE section below and build it independently, without needing to read the other sections first, and without needing the rest of the codebase to exist yet. All cross-module dependencies are pinned down as explicit interfaces/contracts in Section 2. If you're an agent picking up a work package, read Section 1 (context) and Section 2 (contracts) in full, then only your assigned Section 4.x package.

---

## 1. Project Context

We're building a live hackathon demo: a **human and an AI bot race on Wikipedia**. Both start on the same article and must reach the same target article, moving only by clicking links that appear in the article body — the classic "wiki race" game. It runs live on a projector at a hackathon.

**Locked decisions (do not revisit / re-litigate these):**
- It's human vs. bot, not bot vs. bot.
- The human races on their own real laptop/browser. That is **out of scope for code** — it's a physical/projector setup concern only. The human's finish is called manually by whoever is hosting the race.
- The bot is driven by **Steel** — a browser-automation CLI (`steel`) giving cloud-hosted headless browser sessions, controlled via CLI commands. Each team member installs and authenticates it themselves (Section 4.B); confirm your machine is ready with `steel doctor --preflight`. Do not assume it is already set up — it was not installed on at least one team machine as of this amendment. See Section 2.3 for the commands we rely on.
- The bot's link-picking decision at each step is made by an LLM (**Claude**, via the Anthropic API) reasoning over the current article, the target, and the list of candidate links.
- The host manually types in the start and target article for each race — no randomization logic needed.
- The bot **auto-detects its own win** by comparing the current page's **canonical title** to the target after every hop. **Not the URL.** MediaWiki serves redirects *in place* — verified 2026-09-12: `GET /wiki/Obama` returns HTTP 200 with **zero** redirects, the URL still reads `/wiki/Obama`, and the page is *Barack Obama* with `<link rel="canonical" href=".../Barack_Obama">`. Same for `/wiki/Snakes` and `/wiki/WWII`. Since 14-18% of article body links are redirects (`class="mw-redirect"` on the anchor), a URL comparison both misses wins the bot has already achieved and makes any race unwinnable whose target the host typed as a redirect. The canonical title is read out of the HTML we already fetch, so this costs zero extra round trips. There is a hop limit (default 25) so a live demo never hangs forever.
- **How the bot moves: it navigates to the chosen link's URL.** It does not drive a synthetic mouse click. Decided 2026-09-12; this supersedes the looser wording of the game rule above. The legal move set is unchanged and is enforced by `links.extract_candidates` — the bot can only move to a `/wiki/` article link that was present inside `#mw-content-text` on the page it was standing on. Rationale and the four defects this deletes are in the movement note at the end of Section 2.2.
  - **The obligation this creates:** because the browser is no longer the thing enforcing the rule, *our extractor is*. So the reasoning log must name the anchor text it chose, exactly as it appeared on the page ("On *Cat*, target *Nuclear weapon* — clicking **"Physics"** because…"). That is what the audience reads anyway, and it is the answer to "how do we know it is not just jumping to arbitrary URLs?". Package A keeps `Candidate.text` for precisely this; Package D renders it.
- **Projector layout** (3 panes, side by side): human's own browser | Steel's live-view of the bot's browser | a terminal showing the bot's live-updating reasoning log (one line per hop: "On X, target Y — clicking Z because ...").
- **Language: Python.** The bot orchestration shells out to the `steel` CLI via `subprocess` (not a rewritten API client). **Status of that interface: PARTIALLY UNVERIFIED - treat every JSON field name in this document as a guess until Section 3 says otherwise.** Exploratory testing confirmed the general shape of the output, not the flag name and not the literal field names. The Steel reference bundled in this repo documents `--raw` (on `sessions` and `captcha` only) and does not mention `--json` at all; the shipped CLI *does* accept `--json` globally, so the reference is stale rather than the plan being wrong - but that was luck, not verification, and the reference is stale in other ways too (it still documents `sessions --raw` and `snapshot -C`, both gone, and omits `snapshot -u`). Section 3 is the gate.
- **This is a hackathon demo tool, not a production service.** Keep everything as simple as it can be while still working reliably live on stage. No web backend, no database, no auth beyond the two required API keys.

**Required environment/credentials** (every team member needs both):
- `STEEL_API_KEY` — Steel account API key (from steel.dev dashboard, or `steel login`)
- `ANTHROPIC_API_KEY` — Anthropic API key

**Repo setup note:** already done - this file is committed at `github.com/kieran-ym/WikiRacer`; branch off `main`. What *is* outstanding is **step zero** (Section 3): one person runs the probe, commits `docs/steel-json-shapes.md`, and commits the shared files nobody else can start without (Section 2.5). Nobody starts a package until that commit lands. Budget 30-45 minutes.

---

## 2. Shared Contracts (read this before touching any package — this is what makes parallel work possible)

Every package below is built against these interfaces. If you're implementing Package A, you don't need Package B to exist — you just need to produce something that matches these shapes, and you can write your own throwaway test data that matches them too.

> **Amendment log - v1 -> v2 (2026-09-12).** Six changes, all forced by defects found in review. If you built against v1, these are the deltas:
> 1. `Candidate.href` is now **absolute** (`https://en.wikipedia.org/wiki/...`), because that is what Wikipedia actually serves. `is_redirect` and `ref` added.
> 2. `PickResult.candidate` is now `Candidate | None`, and `choose_link` raises `NoCandidatesError` on an empty list - v1 specified an unsatisfiable contract *and* a mandatory unit test that could not pass.
> 3. `HopEvent` gained `target_title` and `t_s`; `RaceResult` gained `elapsed_s`, `winner` and `path`. A race with no clock is not a race.
> 4. `SessionHandle` gained `id` (the field the Steel reference designates for machine parsing) and `session_timeout_ms`.
> 5. `steel_client`: `start_session` takes `session_timeout_ms`; `wait_load` replaced by `wait_for_url`; **`resolve_click_ref`, `snapshot_refs` and `click` struck entirely** — the bot navigates (Locked Decision, Section 1; movement note below). `wiki.py` gained `canonical_title_from_html` and `url_from_title`; `links.py` gained `find_target`.
> 6. `display` gained `start_display`/`stop_display` - v1 mandated `rich.live.Live` through bare module-level functions with no lifecycle, which is not implementable.
>
> **The rule below is unchanged and now doubly important** - but do not silently re-freeze around a defect. If the probe contradicts something here, amend this log and tell everyone.

### 2.1 Data types (conceptually — implement as Python `dataclass`es, one shared `speedrun/types.py` module)

```python
@dataclass
class Candidate:
    index: int         # position in the numbered list shown to the LLM. **0-BASED.** See 2.4.
    text: str          # visible anchor text shown to the LLM, e.g. "Renaissance"
    title: str         # canonical Wikipedia article title, e.g. "Renaissance"
    href: str          # ABSOLUTE href exactly as found in the HTML, e.g.
                       #   "https://en.wikipedia.org/wiki/Renaissance"
                       # Wikipedia serves Parsoid HTML: body links are absolute, NOT "/wiki/...".
    is_redirect: bool  # True if the anchor carried class="mw-redirect", i.e. this link may land
                       # on a differently-titled article. Matters for the win check.
    # (v1 had a Steel @eN ref here for click-resolution. Not needed: the bot navigates. See 2.2.)

@dataclass
class PickResult:
    candidate: Candidate | None  # None is NOT a clickable pick. Optional only so the type can
                                 # carry a degraded result; race.py must treat None as a dead end.
    reason: str        # one short sentence, shown in the reasoning log
    was_fallback: bool # True if the LLM call failed/was invalid and we fell back deterministically

@dataclass
class HopEvent:
    hop: int
    current_title: str   # CANONICAL title of the page we are standing on
    target_title: str    # canonical target. Needed to render the log line Section 1 specifies.
    t_s: float           # seconds since GO, for the projector and the post-race summary
    picked: PickResult

@dataclass
class RaceResult:
    won: bool
    winner: str                    # "bot" | "human" | "none". Only the host calling the human's
                                   # finish can set "human".
    elapsed_s: float               # wall-clock from GO to the end. THE headline number.
    hops: int | None = None
    path: list[str] | None = None  # canonical titles, start first - for the post-race replay
    reason: str | None = None      # exactly one of: "won" | "hop_limit_reached" | "bot_stuck"
                                   #   | "dead_end" | "human_finished_first" | "error"
    error: str | None = None

@dataclass
class SessionHandle:
    id: str            # stable session id. The Steel reference says to use THIS for machine
                       # parsing, not the name. Log it - you need it to stop a leaked session.
    name: str          # the --session name we chose, e.g. "speedrun-1770000000"
    live_url: str      # projector URL for Steel's live view. The probe must confirm whether the
                       # JSON key is `live_url` or `liveUrl`. Do not guess: wrong key -> None on
                       # the projector.
    session_timeout_ms: int  # echo back what Steel actually granted, so the host can see the
                             # session clock. THIS is the timeout that ends a race (see 2.3).
```

### 2.2 Function-level interfaces each package must implement

```python
# speedrun/links.py  (Package A)
def extract_candidates(html: str, max_candidates: int = 1000) -> list[Candidate]: ...
    # v2: 1000, not 300. Wikipedia articles carry 457-1598 body candidates; 300 in document
    # order silently discarded 34-73% of them, including one-hop wins. See 4.A.
def find_target(candidates: list[Candidate], target_title: str) -> Candidate | None: ...
    # Called BEFORE every picker call and BEFORE truncation. If the target link is on this page,
    # click it deterministically - no LLM call, no chance of an LLM error at the winning move.

# speedrun/wiki.py  (Package A)
def canonical_title_from_html(html: str) -> str: ...
    # THE win-check primitive. Read <link rel="canonical">, fall back to <h1 id="firstHeading">.
    # Never derive the title from the URL - see the redirect verification in Section 1.
def title_from_url(url_or_title: str) -> str: ...  # normalization helper only, NOT for win checks
def url_from_title(title: str) -> str: ...         # "Snake" -> ".../wiki/Snake" (percent-encoded)
def titles_match(a: str, b: str) -> bool: ...

# speedrun/picker.py  (Package C)
class NoCandidatesError(Exception): ...   # raised, never returned. No API call is made.

def choose_link(
    client,                      # an anthropic.Anthropic instance, INJECTED so tests pass a mock
    model: str,
    current_title: str,
    target_title: str,
    visited: list[str],          # canonical titles already stood on, INCLUDING the start article
    candidates: list[Candidate], # already visited-filtered and RENUMBERED by the caller
    hop: int,
    max_hops: int,
    banned_titles: set[str] | None = None,   # candidates a stuck retry already proved dead
) -> PickResult: ...

# speedrun/steel_client.py  (Package B)
def start_session(session_timeout_ms: int = 900_000,
                  inactivity_timeout_ms: int = 0) -> SessionHandle: ...
    # BOTH timeouts are required and they are INDEPENDENT. See trap 1 in 2.3.
def navigate(session_name: str, url: str, wait_until: str = "domcontentloaded") -> None: ...
    # This is how the bot MOVES (see the movement note below). Not networkidle: nothing we read
    # depends on network quiet, and networkidle costs seconds per hop.
def wait_for_url(session_name: str, expected: str, timeout_ms: int = 15000) -> bool: ...
    # Waits on the CONDITION (`wait -u <substr>`); returns False on timeout, does NOT raise and
    # does NOT swallow-and-continue. Replaces v1's wait_load - see 4.B for why that mattered.
def get_url(session_name: str) -> str: ...         # diagnostics/logging only, NOT the win check
def content(session_name: str) -> str: ...         # raw page HTML. The single source of truth.
# NOTE: no snapshot/click functions. The bot navigates (see the movement note below), so Steel
#   never needs to resolve an element ref. This is the single biggest simplification in v2.
def stop_session(session_name: str) -> None: ...      # idempotent: "session not found" == success

# speedrun/display.py  (Package D)
def start_display() -> None: ...   # enter the rich Live context. MUST run before any log_hop.
def stop_display() -> None: ...    # exit it. Idempotent; safe in a finally block.
                                   # v1 mandated rich.live.Live through bare module functions with
                                   # no lifecycle and no Live handle, which cannot be implemented.
def print_live_url(live_url: str, session_timeout_ms: int) -> None: ...
def wait_for_go() -> None: ...     # blocks on Enter, so the bot does not start hopping while the
                                   # host is still pasting the live URL onto the projector
def countdown(n: int = 3) -> None: ...
def log_hop(event: HopEvent) -> None: ...
def log_stuck(hop: int, candidate: Candidate, retry_count: int,
              old_url: str, new_url: str) -> None: ...
                                   # log BOTH urls: makes a false positive visible on screen
def announce_result(result: RaceResult) -> None: ...
                                   # ONE banner for every ending, always showing elapsed_s.
                                   # Replaces v1's three announce_* functions, none of which
                                   # could express "the human finished first".
def log_error(exc: Exception) -> None: ...

# speedrun/race.py + cli.py  (Package E - integration)
def run_race(start: str, target: str, model: str, max_hops: int = 25) -> RaceResult: ...
    # start/target are title-OR-url exactly as the host typed them; race.py canonicalizes both
    # before hop 1 (4.E step 3). v1 took *_url while the CLI advertised titles, and nothing
    # owned the conversion.
```

**How the bot moves - read this before building B or E.** The bot navigates directly to `candidate.href`. It does **not** resolve a Steel element ref and click it. This is a v2 change and it deletes `resolve_click_ref` from the plan.

Rationale: v1 pulled the page's link set *twice* per hop - once as HTML via `content` (measured 1.0 MB on *Python (programming language)*, 2.8 MB on *Barack Obama*) and again as an accessibility tree via `snapshot` - then spent its single most fragile function reconciling the two copies. All three of v1's reconciliation strategies were broken. `snapshot` exposes no href field at all without the undocumented `-u`. Wikipedia anchor text is routinely non-unique (piped links), so text matching silently clicks the wrong article. And the CSS fallback `a[href='{href}']` throws on any title containing an apostrophe - `Monty_Python's_Flying_Circus` is on our own demo start page, and Parsoid emits the apostrophe literally (only 1 percent-escape across 1,051 body hrefs on that page). The accessibility tree also omits hidden nodes, so for collapsed-template links neither ref nor text can match and the broken selector path becomes the *routine* one.

Navigating to an href that was present in the article body satisfies the game rule in Section 1: the constraint is on which links are legal moves, not on the input mechanism, and `extract_candidates` is what enforces it. **This is now a Locked Decision (Section 1), not a proposal** — the team chose it over the click path on 2026-09-12, so `snapshot_refs`, `click` and the `--click-mode` flag are gone from this plan rather than parked behind a flag. Do not build them.

What we gave up by choosing this, stated plainly so nobody is surprised by the question on stage: with a real click, the *browser* proves the link existed, because the move is physically impossible otherwise. With navigation, *our extractor* proves it. The mitigation is in Section 1 and it is one line of display code — log the anchor text as it appeared on the page. If the team ever wants the structural guarantee back, the only viable implementation is `snapshot -i -u` supplying a URL per element (anchor-text matching is ambiguous on Wikipedia and the CSS-selector path throws on apostrophes), so start by confirming that flag.

**Rule for every package:** if you need to change one of these signatures, that's a cross-team decision — post it in the team chat/PR description, don't just silently change it, since other packages are being built against the signature as written.

### 2.3 Steel CLI commands we rely on

**The confidence column is part of this table. Respect it.** The subcommand *vocabulary* below is trustworthy - every one of these exists with this shape. The *output contract* is not, and neither was v1's heading, which said "confirmed to exist" about a list inherited from a reference that had drifted.

One copy-pasteable argv per operation. `--json` goes on **every** command. It is a global flag, and it is also auto-enabled when stdout is not a TTY - which is exactly how you get bitten by a TTY difference between your laptop and the demo machine, so pass it explicitly. Errors print to **stdout**, not stderr (see 4.B).

| # | argv | Returns | Confidence |
|---|---|---|---|
| 1 | `steel browser start --session <name> --session-timeout 900000 --inactivity-timeout 0 --json` | session record | shape **unverified** (`live_url` vs `liveUrl`) |
| 2 | `steel browser navigate <url> --session <name> --wait-until domcontentloaded --json` | exit code | verified |
| 3 | `steel browser wait -u <url-substring> --session <name> --timeout 15000 --json` | exit code | verified; `-u` honours `--timeout` |
| 4 | `steel browser content --session <name> --json` | **string** in an envelope | envelope **unverified** |
| 5 | `steel browser get url --session <name> --json` | **string** in an envelope | envelope **unverified** |

Not in the table on purpose: `snapshot` and `click`. The bot navigates, so it never resolves an element ref. If you find yourself reaching for either, re-read the movement note in 2.2 first.
| 8 | `steel browser stop --session <name> --json` | exit code | verified; already idempotent |

**Three traps, all of which bit v1:**

1. **`--session-timeout` is the flag that keeps a race alive, not `--inactivity-timeout`.** They are independent. `--inactivity-timeout 0` disables the 2-minute *idle* reaper. `timeout` is a *separate* hard cap on total session lifetime that **defaults to 300000 ms (5 minutes)** and is **create-time only** - it cannot be raised once the session exists. The clock starts at `start`, i.e. before the host has copied the live URL onto the projector. Five minutes is very plausibly less than setup + crowd commentary + a 25-hop race, and when it expires every subsequent command fails with no recovery path anywhere in this plan. `900000` is the Launch-tier ceiling; raise it if you are on Scale. Our own bundled `SKILL.md` passes `--session-timeout 3600000`; v1 copied the inactivity guidance from the reference and dropped this one.
2. **Items 4 and 5 return a bare string inside an envelope**, roughly `{"success": true, "data": "<string>"}` — they are not structured records. Write your parser against Section 3's recorded output, not against an imagined field name.
3. **Row 5 (`get url`) is for logging only.** The win check reads the canonical title out of row 4's HTML — see Section 1. Do not reintroduce a URL comparison here.

Full reference: `.agents/skills/steel-browser/references/steel-browser-commands.md` and `steel-browser-lifecycle.md` in this repo (vendored via `npx skills add steel-dev/skills --skill steel-browser`). **The `.claude/...` path v1 cited is wrong** - it resolves only through a symlink; the tracked location is `.agents/`. Treat that reference as *stale where it disagrees with this table*: it omits `--json` and `snapshot -u` entirely and still documents `sessions --raw` and `snapshot -C`, both gone. `steel browser <cmd> --help` on the installed CLI beats both documents.

### 2.4 Claude tool-call contract (Package C owns the implementation, but this shape is fixed)

```python
CHOOSE_LINK_TOOL = {
    "name": "choose_link",
    "description": "Pick exactly one candidate link to click next in the Wikipedia speedrun.",
    "strict": True,   # sibling of "name" - NOT inside input_schema, NOT on tool_choice.
                      # additionalProperties:False is inert on its own; "strict" enforces it.
                      # Supported on both models below.
    "input_schema": {
        "type": "object",
        "properties": {
            "link_index": {
                "type": "integer",
                "description": (
                    "The 0-BASED index of your chosen link, copied verbatim from the number "
                    "at the start of that line in the candidate list. The list starts at 0."
                ),
            },
            "reason": {"type": "string", "description": "One short sentence (<=20 words) explaining the choice."}
        },
        "required": ["link_index", "reason"],
        "additionalProperties": False
    }
}
# tool_choice={"type": "tool", "name": "choose_link"} - always force the tool call, no freeform
#   text turn. Valid on both models below (forced tool use only 400s on Fable/Mythos 5.1).
# temperature=0 - REQUIRED. The default is 1.0, which would make 4.E's acceptance dry-run tell
#   you nothing about what the stage run will do. Coupling: at 0, re-asking the same list returns
#   the identical pick, so a stuck retry MUST drop the dead candidate (4.E step 4).
# max_tokens=300 - fine on Haiku. See the Sonnet warning below.
# default model: "claude-haiku-4-5"  <- the alias. Do NOT append a date suffix. (The dated id
#   "claude-haiku-4-5-20251001" that v1 used is real and works, so this is hygiene, not a bug.)
# swappable via --model flag, e.g. "claude-sonnet-5" for stronger picks.
#
# **`--model claude-sonnet-5` is a BROKEN advertised path until you fix it.** Sonnet 5 runs
#   adaptive thinking when `thinking` is omitted, and max_tokens caps thinking + response
#   TOGETHER - so max_tokens=300 truncates before the choose_link block lands and the fallback
#   fires on EVERY hop. That yields a 100%-fallback bot that still looks like it is working:
#   the worst live-demo failure mode there is. Either pass thinking={"type": "disabled"}, or
#   keep adaptive with output_config={"effort": "low"} and max_tokens=2000. The Haiku default
#   path is unaffected (Haiku 4.5 does not think by default).
#
# On model choice: "fast and cheap" is the wrong frame. A full race costs 4-10 cents either way,
#   and each hop costs SECONDS of browser round-trips against ~1s of LLM latency - so a model
#   that reaches the target in 3 fewer hops is faster end-to-end, not slower. Pick on hop count.
#   Run the dry runs on Haiku; try Sonnet 5 (thinking fixed) before you commit for the stage.
```

---

### 2.5 Ownership of the shared files (v2 - v1 left these unowned)

Six files nobody owned in v1, four of which every other package imports. **All six are committed by whoever runs Section 3, before anyone starts a package.**

| File | Owner | Note |
|---|---|---|
| `speedrun/types.py` | step zero | the 2.1 dataclasses. A, C, D and E all import it. |
| `speedrun/__init__.py` | step zero | empty file; without it nothing imports. |
| `.env.example` | step zero | **and a loader** - see 4.E. `.gitignore` already ignores `.env`. |
| `conftest.py` (repo root) | step zero | empty file. Without it `pytest tests/test_links.py` fails with `ModuleNotFoundError: No module named 'speedrun'` - reproduced on pytest 9.1.1. v1's acceptance criteria for both A and C specify exactly that failing command. |
| `docs/steel-json-shapes.md` | step zero | the probe output. Package B's ground truth. |
| `tests/fixtures/python_programming_language.html` | step zero | one `curl`. See 4.A - the highest-value file in the repo. |

**Python 3.10+** is required (`int | None` in `types.py`). Say so in the README.

## 3. Step Zero - the probe (30-45 min, ONE person, BLOCKS EVERYTHING)

This is no longer "whoever starts first should do this". Nobody starts a package until this lands, because Section 2's output contract is a guess until it runs, and two of the things it settles (`snapshot -u`, the `content` envelope) change what Packages A and B build.

**v1's probe did not execute.** `steel browser navigate https://en.wikipedia.org/wiki/Python_(programming_language)` has unquoted parentheses: bash/sh give `syntax error near unexpected token '('`, and zsh - the macOS default, which is what this team is on - gives `zsh:1: unknown sort specifier`. Because the six lines ran independently, `start` would succeed, `navigate` would die in one line of shell noise between two walls of JSON, and `get url` / `content` / `snapshot` would all **succeed against `about:blank`**, producing well-formed, plausible, completely wrong output. v1 then told the runner to paste that in as "ground truth instead of guessing" - so Package B would have read `get url -> "about:blank"` and an empty snapshot, concluded the scoped snapshot does not work on this CLI, and abandoned it before ever testing it. Hours of wrong work on the component this plan itself calls the riskiest.

```bash
set -euo pipefail
export STEEL_API_KEY=...
steel --version                      # record this; the CLI drifts and our vendored docs are stale
steel doctor --preflight             # auth must pass BEFORE you interpret anything below

URL='https://en.wikipedia.org/wiki/Python_(programming_language)'   # QUOTED. This was the v1 bug.
S=probe

steel browser start    --session "$S" --session-timeout 900000 --inactivity-timeout 0 --json
steel browser navigate "$URL" --session "$S" --wait-until domcontentloaded --json

# ---- GATE: stop and LOOK. If this is not the Wikipedia URL, everything below is garbage. ----
steel browser get url  --session "$S" --json

steel browser content  --session "$S" --json | head -c 400; echo
steel browser content  --session "$S" --json | wc -c
steel browser snapshot -i    -s "#mw-content-text" --session "$S" --json | head -40
steel browser snapshot -i -u -s "#mw-content-text" --session "$S" --json | head -40  # OPTIONAL, see below
steel browser find     "#mw-content-text a"        --session "$S" --json | head -20
steel browser wait -u 'Python' --session "$S" --timeout 5000 --json; echo "wait exit=$?"
steel browser get attr @e1 href --session "$S" --json

steel browser stop --session "$S" --json
steel browser stop --session "$S" --json     # must ALSO succeed: we depend on idempotence
steel browser sessions --json                # must show nothing of ours left running
```

**The five questions this exists to answer.** Write the answer to each *explicitly* in `docs/steel-json-shapes.md`, not just raw output - the next reader will not re-derive them:

1. Is the live-view key `live_url` or `liveUrl`? What is the session `id` field, and what `timeout` did Steel actually grant? (Wrong key here = `None` on the projector.)
2. What exactly wraps the `content` / `get url` / `snapshot` payloads? Record the envelope **plus the first ~300 chars plus the byte length** - do not try to paste a 1 MB page. That is precisely why this shape is the one most likely to go unrecorded.
3. *(Optional, no longer blocking.)* Does `snapshot -i -u` emit per-element urls? Nothing in the plan needs it now that the bot navigates — record the answer in one line anyway, because it is the gate on ever restoring the real-click path, and you are already sitting here with a live session.
4. Where does an error go - stdout or stderr - and what is the exit code? 4.B's error messages depend on it; v1 said "include the raw stderr" and stderr appears to be empty.
5. Does `wait -u` actually honour `--timeout`? Time it. (The `--load` branch reportedly ignores it in favour of a hardcoded ~25s.)

**While you are here, same sitting, ~10 more minutes:** commit the six shared files in Section 2.5, including `curl`ing the fixture in 4.A. Then post "Contracts v2 confirmed" - or the amendments the probe forced - in the team chat. *That* is the green light for parallel work.

---

## 4. Work Packages (parallelizable)

Packages A, B, C, D have **no dependency on each other's code** - only on the shared contracts in Section 2. They can be built simultaneously by four different people/agents. Package E (integration) is the only one that assembles the others, so it is either done last, or scaffolded in parallel against mock/stub versions of A-D and wired up for real once they land.

**Two v2 caveats on that claim:**
1. **Nothing starts until step zero (Section 3) is committed.** Four of the six shared files in 2.5 are imported by every package, and the probe settles contracts that A and B are built against. Parallel work that starts before that commit is parallel work against a guess.
2. **Package B's smoke test imports Package A.** That is deliberate and new - see the note under 4.B. It is the only gate before the full end-to-end run where the link extractor meets a real page over the wire, and v1's routing-around of it is why the extractor's blocker survived every check in the document.

### 4.A — Pure Logic: Link Extraction & Wiki Title Matching
**Owns:** `speedrun/links.py`, `speedrun/wiki.py`, `tests/test_links.py`, `tests/test_wiki.py`
**Dependencies:** none (no Steel account or Anthropic key needed — fully offline)
**Can start immediately.**

Build:
> **BLOCKER FIXED IN v2 - read before writing a line.** v1 step 3 said "keep only `href` starting with `/wiki/`". That returns **zero candidates on every real Wikipedia article**, so the bot never takes a hop. en.wikipedia.org serves Parsoid read-view HTML in which every article-body link is **absolute**. Verified 2026-09-12 on our own demo start page: **1,052** `href="https://en.wikipedia.org/wiki/..."` anchors (1,042 carrying `rel="mw:WikiLink"`) against **66** relative ones - and all 66 are site chrome (`/wiki/Main_Page`, `/wiki/Special:Random`, `/wiki/Wikipedia:About`) sitting outside `#mw-content-text`. Reproduced on *Snake*, *World War II*, *Renaissance*, *Cat* and *Barack Obama*: zero relative in-body links on any of them.
>
> What made this worth a blocker rather than a one-line fix is the *second half* of v1's spec: it mandated hand-written inline HTML fixtures. Those would have been written with `/wiki/Foo` hrefs - self-consistent with the wrong assumption - so the suite would go green while the function returned `[]` in production, and nothing else in v1's 307 lines ever ran this code against a real page. Hence the mandatory real fixture below.

- `links.extract_candidates(html, max_candidates=1000) -> list[Candidate]`:
  1. Parse with **`BeautifulSoup(html, "html.parser")`** - name the backend. `"lxml"` is what most people reach for and raises `FeatureNotFound` against our `requirements.txt`. Scope to `#mw-content-text` (fall back to the whole doc if that selector is missing, so it degrades instead of crashing).
  2. Remove subtrees matching `.reflist, .reference, ol.references, .navbox, .sidebar, .side-box, .sistersitebox, .metadata, .portalbox, .navbar, .mw-editsection, [hidden]` before collecting `<a>` tags.
     - **`.sidebar` is the important addition.** On *Python (programming language)* - our own demo start page - **151 of the 300 candidates v1 would have shown the LLM sat inside a single `.sidebar` navigation template.** Half the first-hop budget spent on chrome, and a `.sidebar` is just a vertical navbox, which v1 already stripped.
     - **Keep `.infobox`** - correct as v1 had it. Its 69 links on the Python page are legitimate moves.
     - **Drop `.hatnote` from the strip list.** Hatnotes are body content and are frequently literal inline "See also:" lines - exactly the lateral move that wins races.
     - `.reflist` and `.mw-editsection` match nothing in current HTML (`ol.references` does the work). Harmless; keep for older cached HTML.
  3. Accept an href matching `^(?:https?://en\.wikipedia\.org)?/wiki/(?P<title>[^?#]+)$` - **absolute or relative**. Reject any href carrying a host other than `en.wikipedia.org`: real article bodies contain cross-wiki and plain external links, including things like `code.google.com/p/.../wiki/...` that would otherwise match on `/wiki/`.
  4. Skip these namespace prefixes after `/wiki/`: `File:`, `Category:`, `Special:`, `Help:`, `Portal:`, `Template:`, `Template_talk:`, `Module:`, `Draft:`, `User:`, `User_talk:`, `Wikipedia:`, `Wikipedia_talk:`, `MediaWiki:`, `TimedText:`, `Book:`, `Talk:` (exact prefix match on the segment before the first `:` inside the title, **not** a "contains a colon" check - legitimate titles like *Batman: The Animated Series* must survive). Do not spend time extending this list: across ~8,000 real body links measured on four articles there were **zero** hits on any further namespace or alias, because Parsoid resolves aliases before emitting the href.
  5. Skip `href`s containing `#cite_note` or `#cite_ref`, and skip self-links to the current article.
  6. URL-decode the title portion, replace `_` with space -> `Candidate.title`. Anchor's visible text (`a.get_text(strip=True)`, falling back to **`Candidate.title`** - not the `<a title=...>` attribute; v1 was ambiguous) -> `Candidate.text`. Set `Candidate.is_redirect` from `class="mw-redirect"` on the anchor: it sits on the anchor itself, so we can know *before* moving that a link may land on a differently-titled page.
  7. Dedupe by `title`, keeping first occurrence (document order). Truncate to `max_candidates`, assign `index` 0..N-1 **in the final order**. `Candidate.index` is what gets rendered to the model and is **0-based** - see 2.4.

  **On `max_candidates`:** v1's 300 was not a safety margin, it was a silent 34-73% discard. Measured candidate counts: *Python* 457, *World War II* 1,108, *United States* 1,598. Document order front-loads the infobox and lead, so it behaves more like a relevance prior than it sounds - but real directly-linked targets fall outside it (*Nuclear weapon* sits around index 900 on *World War II*) and every late "See also" link is dropped. 1,598 candidates is roughly 20K tokens in a 200K window at about $0.02/hop, so the cap has no justification. Raised to 1000; if you want it lower, tag candidates by section rather than truncating blind.

- `links.find_target(candidates, target_title) -> Candidate | None`: return the candidate whose title matches the target, if any. **`race.py` calls this before every picker call and moves there deterministically** - no LLM call, no chance of an LLM error at the winning move, one less hop of latency. Most wiki races end with the target link visible one hop early, so this is the highest-value-per-line function in the project. It must run **before** truncation.
- `wiki.canonical_title_from_html(html)`: read `<link rel="canonical">` (fall back to `<h1 id="firstHeading">`) and normalize. **This is the win-check primitive** - see the redirect verification in Section 1. Do not implement the win check against the URL.
- `wiki.title_from_url(url_or_title)`: if the input contains `/wiki/`, take the segment after it; URL-decode, replace `_` with space, strip any `#fragment`. If it is already a bare title, clean it the same way. Normalization helper only - **not** for win checks.
- `wiki.url_from_title(title)`: the inverse. Percent-encode; `"Snake"` -> `"https://en.wikipedia.org/wiki/Snake"`. Needed because the CLI takes title-or-url and nothing in v1 owned the conversion.
- `wiki.titles_match(a, b)`: run both through the same normalization and compare case-insensitively.

Tests:

**The mandatory one, first.** Commit `tests/fixtures/python_programming_language.html`:

```bash
curl -A 'WikiRacer/1.0 (hackathon project; https://github.com/kieran-ym/WikiRacer)' \
  'https://en.wikipedia.org/wiki/Python_(programming_language)' \
  -o tests/fixtures/python_programming_language.html
```

(Descriptive User-Agent per the Wikimedia UA policy.) Then assert:
- `len(extract_candidates(fixture)) > 200`
- a named known body link is present (e.g. `"Guido van Rossum"`)
- **no** candidate title starts with any blocked namespace prefix
- `find_target(extract_candidates(fixture), "Guido van Rossum")` is not None

It is a committed file, so Package A stays fully offline and credential-free - the acceptance criterion below is unchanged. **This one test is what moves this package's worst failure mode from "discovered on stage" to "discovered before lunch",** which is why it is listed before the unit tests rather than after.

Then the unit fixtures (inline HTML strings, no network). **Write their hrefs in the absolute form** - an inline fixture using `/wiki/Foo` agrees with a bug instead of catching it:
- A fixture `#mw-content-text` div containing: 2-3 legit absolute `https://en.wikipedia.org/wiki/Foo` links, a duplicate of one, a relative `/wiki/Bar` link (must still be accepted), a cross-host `https://code.google.com/p/x/wiki/Y` link (must be rejected), a `/wiki/File:X.jpg` link, a `/wiki/Category:Y` link, a `<sup class="reference">` citation anchor, a `<div class="reflist">...</div>` block, and a `<div class="sidebar">` holding 3 links -> assert `extract_candidates` returns exactly the expected filtered/deduped/ordered list.
- A fixture with more than `max_candidates` links -> assert truncation, and assert `index` is contiguous 0..N-1 afterwards.
- An anchor with `class="mw-redirect"` -> assert `is_redirect` is True.
- `title_from_url` on a bare title, a percent-encoded/underscored URL, and a URL with `#fragment`. Include a real apostrophe title (`Monty_Python's_Flying_Circus`) and `%26` / `%C3%A9` cases.
- `url_from_title` round-trips with `title_from_url`.
- `canonical_title_from_html` on a snippet whose `<link rel="canonical">` disagrees with its URL -> the canonical wins.
- `titles_match` across case differences, underscore-vs-space, and a clear non-match.

**Acceptance criteria:** `python -m pytest tests/test_links.py tests/test_wiki.py` passes, 100% offline, no env vars needed. Also ship a throwaway `python -m speedrun.links <file.html>` that dumps the candidate list, so anyone can eyeball it in five seconds.

---

### 4.B — Steel Browser Client
**Owns:** `speedrun/steel_client.py`
**Dependencies:** an authenticated `steel` CLI, and the probe output from Section 3.

Install with the native installer: `curl -fsS https://setup.steel.dev | sh`. **Not** `npm install -g @steel-dev/cli` - reproduced: `npm warn deprecated @steel-dev/cli@0.3.1: Steel CLI is now distributed as a native binary.` The npm path still works as a shim, but Package E teaches this to the whole team in the README, so get it right here. Then `steel login` (or export `STEEL_API_KEY`) and confirm with `steel doctor --preflight`.

**Blocked until step zero (Section 3) lands.** That is the change from v1, which said "can start immediately once the probe has run" while scheduling the probe as a parallel task.

Build a thin `subprocess`-based wrapper implementing every function signature in Section 2.2. Guidelines:
- Every call passes `--json` explicitly (do not rely on the not-a-TTY auto-enable) and parses stdout with `json.loads`, unwrapping the envelope the probe recorded. Raise a clear exception on non-zero exit **including the captured stdout, not just stderr** - the probe should confirm Steel prints errors to stdout and leaves stderr empty, which would have made v1's "include the raw stderr" produce blank exception messages.
- **Every `subprocess.run` takes a `timeout=`.** v1 had none, so a hung CLI call hangs the demo forever with no output at all. Use `timeout=45` for `content`/`snapshot` and `timeout=20` for the rest, and raise a distinct `SteelTimeout` so `race.py` can tell "Steel is wedged" from "the page did not change".
- `start_session`: `steel browser start --session <generated-name> --session-timeout 900000 --inactivity-timeout 0 --json`. **Both flags.** See trap 1 in 2.3: the one that ends a live race is `--session-timeout`, and it cannot be changed after creation. Generate the name yourself, e.g. `f"speedrun-{int(time.time())}"`. Parse `id`, `name`, the live-view URL (`live_url` or `liveUrl` - **use what the probe recorded**) and the granted timeout into a `SessionHandle`.
- `wait_for_url`: `steel browser wait -u <url-substring> --session <name> --timeout 15000 --json`. Return `True` on exit 0, `False` on timeout - **do not swallow and continue.** v1's `wait_load` waited on a *load state* and was specified to swallow timeouts, so it could resolve against the still-idle **old** document and report success before the new page existed. Combined with v1's URL-unchanged stuck check, that turns a perfectly good move into a false "stuck". Returning a bool moves the decision to `race.py`, which has the context to handle it.
- **No `resolve_click_ref`, no `snapshot_refs`, no `click`.** The bot moves with `navigate(candidate.href)` — see the movement note in 2.2 and the Locked Decision in Section 1. This is ~40 lines of the most failure-prone code in v1 that you simply do not write.
- `stop_session`: must not raise if the session is already gone

**Acceptance criteria:** a manual smoke script (not pytest - this needs a live Steel session) that does: start -> `navigate` to a real Wikipedia page -> `get_url` -> `content` -> **`navigate` to an href taken from `links.extract_candidates(content)`** -> `wait_for_url` -> confirm the canonical title changed -> stop -> stop again (idempotence) -> `steel browser sessions` shows nothing left running.

**Note the dependency v1 hid:** that smoke test imports Package A. v1 deliberately routed around it ("resolve_click_ref on a real link found in that content") and listed no dependency on A - which is a large part of why A's blocker survived every gate in the document. Take the five-minute coupling; it is the only place before the full end-to-end run where A meets a real page over the wire.

**Also record:** time one full hop (`navigate` -> `wait_for_url` -> `content`) and write the number into `docs/steel-json-shapes.md`. Nobody has measured this, and 4.E now carries a latency target that needs a baseline.

---

### 4.C — LLM Link Picker
**Owns:** `speedrun/picker.py`, `tests/test_picker.py`
**Dependencies:** `ANTHROPIC_API_KEY` for real calls; tests themselves must NOT hit the network (mock the Anthropic client).
**Can start immediately.**

Build `choose_link(...)` per Section 2.2, using the tool contract in Section 2.4.

**The client is injected** (first parameter), which is how the mandated "mock the Anthropic client" tests are possible at all - v1's signature had no client parameter and no stated injection point, so there was nowhere to put the mock.

Construct it in `config.py` as `anthropic.Anthropic(timeout=8.0, max_retries=1)`. **Both arguments matter.** The SDK defaults are a 10-minute request timeout with 2 automatic retries, and timeouts are themselves retried - so v1, which named "API exception/timeout" as a fallback trigger and then set no timeout, had a worst case around 30 minutes of dead air on stage before the fallback it depends on could fire.

- **System prompt** (fixed): "You are playing a Wikipedia speedrun (wiki race). You start on one article and must reach a target article by moving only through links that appear in the article body. On each turn you will see the current article, the target article, the articles already visited this race, and a numbered list of candidate links from the current article. The list is **0-indexed**: the first line is index 0. Pick exactly one link most likely to lead toward the target in the fewest hops, using your general knowledge of how topics connect on Wikipedia. When the target is far away or narrow, route through a broad hub article first (a country, a century, a field of study, a major organization) and then descend toward the target - do not pick a link merely because it is topically adjacent. Candidates you have already visited have been removed for you. Call `choose_link` with your pick and a single short reason."
- **User prompt per hop**: current article, target article, visited list so far (or "(none yet)"), `hop`/`max_hops`, any `banned_titles`, and the numbered candidate list.
- **Render the list from `Candidate.index` verbatim** - `f"{c.index}. {c.text} -> {c.title}"`. **Never re-enumerate**, and in particular never `enumerate(candidates, 1)`.

  > **Why this gets its own warning.** This is the only silent-wrong-answer bug in the plan. If the render is 1-based while the code validates and dereferences 0-based, the bot moves to the link *after* the one it reasoned about, on every single hop. The value is always in range, so the fallback never fires; 299 of 300 mis-picks pass validation. All four of v1's mandated tests use implementer-chosen canned indices and agree with the code by construction, so the suite goes green. The only visible symptom is the projector's Reason column naming a different article than the Chosen Link column - which at 11pm reads as "the model is making bad picks, switch to Sonnet" and burns an hour on the wrong hypothesis. Pin it in all three places (tool description, system prompt, render expression) and log the raw `link_index` next to the resolved title so a mismatch is obvious on hop 1.

- **Filter `visited` out of `candidates` before numbering** (and say so in the prompt, as the system prompt above does), keeping the unfiltered list only if filtering would empty it. Also drop anything in `banned_titles`. v1 passed `visited` as prose and relied on the sentence "avoid re-visiting an already-visited article unless it's clearly the best option" - advice, not a constraint. The published benchmark for exactly this policy shape (one-step choice + visited history + a step cap) reports loops in roughly 61-66% of trajectories, and with `max_hops=25` a single 2-cycle consumes the whole live demo. Make it structural; delete the soft sentence.
- Call `client.messages.create(...)` with `tool_choice` forcing `choose_link`, `temperature=0`, `max_tokens=300`.
- **Validation** (pull this into a pure `parse_choice(response, candidates, visited)` helper so it is unit-testable without mocking the whole `choose_link` call - v1 got this right and it is worth keeping): require `stop_reason == "tool_use"` with a `choose_link` block present, and `0 <= link_index < len(candidates)`. Parse the tool input with `json.loads`, never string-matching. Consider `disable_parallel_tool_use=True` so you can assume exactly one block.
- **Empty candidate list: raise `NoCandidatesError`, make no API call.** Do **not** route it into the fallback.

  > v1 specified four things that cannot all hold: an empty list as a *fallback trigger*; a fallback action of "pick the first candidate whose title differs from the most recent visited title" (there are no candidates to pick from); `PickResult.candidate` as a non-optional `Candidate`; and a **mandatory unit test** asserting "empty candidates -> fallback triggered without even calling the API". The first person to write that fourth test hits the contradiction and has to invent a return shape Package E was never told about. Section 4.E catches `NoCandidatesError` and returns `RaceResult(reason="dead_end")`.

- **Fallback** - triggered by: `APITimeoutError`, `RateLimitError`, 5xx, wrong `stop_reason` (including a refusal), `stop_reason == "max_tokens"`, or a missing/out-of-range `link_index`. Action: deterministically pick the first candidate not in `visited` and not in `banned_titles`, and return `PickResult(was_fallback=True, reason="[fallback] ...")`.
- **Split fatal from retryable.** `AuthenticationError`, `PermissionDeniedError`, `NotFoundError` and `BadRequestError` must **re-raise**, so `cli.py` prints one clear line and exits. v1 funnelled *every* API exception into the fallback, which means an expired key or a typo'd `--model` produces a full 25-hop race of first-link picks on the projector instead of a diagnosable stop. Add one throwaway `messages.create` preflight at startup so a bad key fails at the terminal in a second.

Tests (mock `client.messages.create` to return canned response objects, no network):
- Valid tool_use response with in-range index -> accepted, `was_fallback=False`.
- Out-of-range `link_index` -> fallback triggered.
- Non-`tool_use` stop reason (e.g. simulate a refusal) -> fallback triggered.
- `stop_reason == "max_tokens"` -> fallback triggered.
- Empty `candidates` list -> **raises `NoCandidatesError`**, and the mock records **zero** calls.
- `AuthenticationError` from the mock -> **re-raised**, not swallowed into a fallback.
- **Index-base regression test:** build 3 candidates, capture the prompt string passed to the mock, and assert the first rendered candidate line starts with `"0."`.
- A visited title present in `candidates` -> absent from the rendered prompt, and the remaining indices are contiguous from 0.


---

### 4.D — Live Reasoning Log Display
**Owns:** `speedrun/display.py`
**Dependencies:** `rich` library only. No Steel or Anthropic dependency at all — can be built and demoed standalone by feeding it fake `HopEvent`s in a `__main__` block.
**Can start immediately.**

**Owns also:** `tests/test_display.py` (v1 said "test both paths" but gave Package D no test file in Section 6).

Build all functions in Section 2.2 using `rich.live.Live` + `rich.table.Table`:
- `start_display()` / `stop_display()` own the `Live` lifecycle and hold the module-level `Live` + `Table`. **This is the v2 addition that makes the package implementable at all:** v1 specified bare module-level functions with no lifecycle and no `Live` handle, so there was no legal place to enter the context and Package E had no way to drive it.
- One persistent `Table` with columns: Hop, Time, Current Article, Chosen Link, Reason (prefix `[fallback]` visually - dim/yellow - when `was_fallback=True`). The Time column is `HopEvent.t_s`; this is a race.
  - **Chosen Link renders `candidate.text` — the anchor text as it appeared on the page — not `candidate.title` and not the URL.** This is load-bearing, not cosmetic: it is the obligation the movement Locked Decision in Section 1 creates. Since the browser no longer proves the link existed, this column is what shows the audience (and a judge) that the bot moved through a link that was really on the page. Put the canonical title next to it in parentheses when they differ, which is exactly the redirect case.
- **Pass `vertical_overflow="visible"` to `Live`, and rebuild the table from a `deque(maxlen=8)`.** The default is `vertical_overflow="ellipsis"`, which keeps `lines[:height-1]` - i.e. it crops the **newest** rows. On a big-font projector terminal a 25-hop table therefore appears to freeze on the early hops mid-race (it does render in full after `stop()`, which is why this is easy to miss in testing). Eight rows of large text is also about what reads from the back of a room.
- `log_hop` appends a row and calls `live.update(table)`.
- `print_live_url` prints the projector URL prominently (a `rich.panel.Panel` in a bright color) at the start of the race so the host can immediately copy it into a browser tab. Print the session clock next to it (`session_timeout_ms`) so the host knows how long the session is good for - see trap 1 in 2.3.
- `wait_for_go()` prints "Live view up on the projector and racer ready? Press Enter..." and blocks. Without it the bot starts hopping while the host is still pasting a URL, which makes the *opening* of the demo structurally un-showable. `cli.py` gets a `--no-gate` to bypass it for dry runs.
- `countdown(3)` renders "3... 2... 1... GO" large. The race clock starts at GO.
- `announce_result(result)` must be visually unmissable from a distance (large colored banner) and must render **every** ending - bot win, human win, hop limit, dead end, stuck, error - always including `elapsed_s`. One function, not v1's three, none of which could express "the human finished first".
- Must **degrade to plain sequential `print()` calls** if `sys.stdout.isatty()` is False (e.g. piped to a log file) - do not let a live demo depend on TTY detection working correctly; test both paths.

**Acceptance criteria:** a `python -m speedrun.display` demo mode that fabricates 5-6 fake hops including one fallback, then each of the five endings, running with no env vars or network at all. **Run it in a 24-row terminal** - that is the check that catches the `vertical_overflow` crop, and an 80x24 window is a fair stand-in for a projector. `tests/test_display.py` asserts the non-TTY path emits plain lines and raises nothing.

---

### 4.E — Race Orchestration, CLI, Config, README (Integration)
**Owns:** `speedrun/race.py`, `speedrun/cli.py`, `speedrun/config.py`, `requirements.txt`, `README.md`
**Dependencies:** the interfaces from Packages A–D (can be stubbed/mocked to start scaffolding early, then wired to the real implementations as they land — this package doesn't have to wait if whoever owns it wants to build against fakes first).

Build:
- `config.py`:
  - Validate `ANTHROPIC_API_KEY` and construct the shared `anthropic.Anthropic(timeout=8.0, max_retries=1)` client (4.C injects it). Raise a clear, host-friendly message - not a stack trace - if it is missing.
  - **Do not hard-check `STEEL_API_KEY`.** Our Python code never reads it; it shells out to `steel`, which resolves its own credentials. A teammate who ran `steel login` - which is exactly the state Section 1 describes - has no such env var and would be blocked from racing by our own preflight. Run `steel doctor --preflight` instead and surface its output on failure.
  - **Load `.env`.** `.gitignore` already ignores it and Section 6 ships `.env.example`, but nothing in v1 read either: no `python-dotenv`, and `config.py` only checked `os.environ`. A teammate who dutifully fills in `.env` gets our carefully-worded "key missing" error while staring at the key. Add `python-dotenv` + `load_dotenv()`, or delete `.env.example` and put two literal `export` lines in the README. Pick one; do not ship half of each.
  - Defaults: `DEFAULT_MODEL = "claude-haiku-4-5"` (the alias - see 2.4), `DEFAULT_MAX_HOPS = 25`, `DEFAULT_SESSION_TIMEOUT_MS = 900_000`, `LLM_TIMEOUT_S = 8.0`, `TARGET_MEDIAN_HOP_S = 3.5`.
- `race.run_race(start, target, model, max_hops=25) -> RaceResult`, calling into `steel_client`, `links`, `wiki`, `picker`, `display`. Structure:
  1. `start_session(session_timeout_ms=900_000, inactivity_timeout_ms=0)`. **Both.** `--inactivity-timeout 0` handles crowd-commentary pauses; `--session-timeout` is what stops the session being hard-killed five minutes in. v1 set only the first and gave the wrong reason for it - see trap 1 in 2.3.
  2. `start_display()`, then `print_live_url(handle.live_url, handle.session_timeout_ms)`.
  3. **Canonicalize both endpoints before hop 1.** `navigate(url_from_title(target))`, read `content`, `canonical_title_from_html` -> the real target title; then the same for the start. This costs one extra page load and it buys three things: it validates that both articles *exist* before the race (a host typo mid-demo otherwise burns all 25 hops), it resolves the "keyword" Section 1 promises into the exact title the win check needs, and it is what makes a redirect target like "Snakes" or "WWII" winnable at all. Also handle `start == target` here. If either lookup fails, `announce_result` with `reason="error"` and a message the host can act on.
  4. `wait_for_go()` (unless `--no-gate`), `countdown(3)`, **start the clock.**
  5. Loop up to `max_hops`:
     - `html = content(...)`; `current = canonical_title_from_html(html)`. **This is the win check** - `titles_match(current, target)`. Not the URL. Append `current` to `path` and `visited`.
     - `candidates = extract_candidates(html)`.
     - `find_target(candidates, target)` -> if hit, move there directly, confirm, and win. No LLM call at the winning move.
     - filter `visited` and `banned`, renumber, `choose_link(...)`, `log_hop(...)`.
     - `navigate(candidate.href)`; `moved = wait_for_url(session, expected_substring)`.
     - If `not moved`: re-read the canonical title, **take a second look ~700 ms later**, and only then count a stuck hop - `log_stuck(...)` with both URLs, add the candidate to `banned`, and **re-call the picker on the same page with that candidate dropped**. (v1 named a retry cap of 5 but never said what a retry *does*, and its stuck signal had two unguarded false-positive paths - see the `wait_for_url` note in 4.B. Five false positives ending a working race as "a clean loss" while the projector visibly shows the bot moving through five correct articles is a screen-contradicts-program failure, the worst kind on stage.)
     - Catch `NoCandidatesError` -> `RaceResult(reason="dead_end")`.
  6. `try/finally`: **always** `stop_session` and `stop_display`, whether the race won, hit the hop limit, dead-ended, got stuck, or raised - a live demo must never leak a running cloud session. (v1 had this and was right to call it non-negotiable.)
  7. Return `RaceResult` with `elapsed_s`, `winner`, `path`.

  **Latency target: median hop <= 3.5s.** v1 stated none, despite competitiveness being the entire point and despite 2.4 justifying the model choice *on latency*. Three things follow. (a) The loop above reads the page **once** per hop; v1's ordering re-read an unchanged page at the top of every iteration with a `wait` + `get url` that the previous iteration's tail had just done. (b) Use `--wait-until domcontentloaded`, not `networkidle` - nothing we read depends on network quiet. (c) If you are still over budget, collapse the hop into one `steel browser batch` call returning a small JSON of canonical title + `[text, href]` pairs, which replaces `content` + parse + both `get url`s; measure before you build it. **No live Steel round trip has been timed yet** - Package B records the baseline (4.B), and this number is a target, not a measurement.
- `cli.py`: `argparse` entrypoint - `python -m speedrun.cli --start "<title-or-url>" --target "<title-or-url>" [--model ...] [--max-hops N] [--no-gate]`. Wrap `run_race` so `KeyboardInterrupt` prints "stopping Steel session..." before exiting cleanly (cleanup is already guaranteed by `race.py`'s `finally`; this is just a friendlier message for the host). Run a daemon thread on `sys.stdin.readline()` during the race so the host pressing Enter stamps the human's finish time, sets `winner="human"`, and ends the bot's race - that is the whole of the human-vs-bot arbitration, and it is about ten lines.
- `requirements.txt`: `anthropic>=1,<2`, `beautifulsoup4>=4.12`, `rich>=13.7`, `python-dotenv>=1.0` (+ `pytest` as a dev dependency). **`anthropic>=0.40` was a pre-1.0 floor left unbounded across a major break** - it resolves to 1.x, which has breaking changes from the 0.x API. Pin the major.
- `README.md` must cover: prerequisites (**Python 3.10+**, `curl -fsS https://setup.steel.dev | sh` + `steel login`, `ANTHROPIC_API_KEY`), install steps, the exact run command, the 3-pane projector layout, and troubleshooting ("if the bot seems to hang, check `steel browser sessions` and `steel browser stop --all`"; "if the session died, it was almost certainly `--session-timeout`"). Open with a one-paragraph **"what you will see when this works"** - a reader needs that in the first 30 seconds and no version of this document has had it.

**Acceptance criteria (end-to-end manual dry run, the primary verification for this whole project):**
```bash
python -m speedrun.cli --start "Python (programming language)" --target "Guido van Rossum" --max-hops 25
python -m speedrun.cli --start "Cat" --target "Nuclear weapon" --max-hops 25
python -m speedrun.cli --start "Snakes" --target "WWII" --max-hops 25   # BOTH endpoints are redirects
```

**On the pair v1 shipped:** `--start "Python (programming language)" --target "Snake"` is a poor demo choice. Of all 457 candidates on that page, **none** links to *Snake*, *Pythonidae*, *Python (genus)* or *Reptile* - it needs at least three hops through no visible bridge. Run 1 above is a one-hop win, which is the fastest way to prove `find_target` and the win check. Run 3 is the redirect regression: it is the run that would have failed on stage under v1, and it must pass.

Confirm each run: live-view URL prints and works, the gate holds until Enter, the countdown fires, hop-by-hop reasoning with times appears in the terminal, the race reaches the target or cleanly reports its reason, `elapsed_s` shows in the banner, and `steel browser sessions` shows nothing lingering afterward. Then repeat once hitting Ctrl+C mid-race, and once pressing Enter mid-race (must report `winner="human"`), re-confirming no lingering session either time.

---

## 5. Integration Order (if not doing true parallel start)

If the team cannot truly parallelize (e.g. only 1-2 people), build in this order: **B -> A -> C -> D -> E** (after step zero, which is not optional in either mode).

**This is reversed from v1, which said B was "the riskiest/least-known part (do it early to surface surprises)" and then scheduled it third of five.** Position three is not early. B goes first because it is the only package whose findings can invalidate Section 2's contracts, and the only one that can validate the assumptions A and C are built on. A follows because its fixture test is the cheapest high-value check in the repo. C needs no live credentials. D is low-risk and fast, and doubles as an offline stage fallback - it demos with fabricated `HopEvent`s and no network at all, which v1 never claimed as the asset it is. E is mostly wiring once A-D exist.

## 6. Repo Structure (final)

```
.
├── PLAN.md
├── README.md
├── requirements.txt
├── .env.example              # ANTHROPIC_API_KEY=...   (Steel uses `steel login`; see 4.E)
├── conftest.py               # empty; without it `pytest tests/...` cannot import speedrun
├── docs/
│   └── steel-json-shapes.md  # output of the Section 3 probe  (step zero)
├── speedrun/
│   ├── __init__.py           # step zero
│   ├── types.py              # shared dataclasses (Section 2.1)  (step zero)
│   ├── config.py             # Package E
│   ├── steel_client.py       # Package B
│   ├── wiki.py               # Package A
│   ├── links.py              # Package A
│   ├── picker.py             # Package C
│   ├── display.py            # Package D
│   ├── race.py               # Package E
│   └── cli.py                # Package E
└── tests/
    ├── fixtures/
    │   └── python_programming_language.html   # one curl (step zero). See 4.A.
    ├── test_wiki.py          # Package A
    ├── test_links.py         # Package A
    ├── test_picker.py        # Package C
    └── test_display.py       # Package D
```
