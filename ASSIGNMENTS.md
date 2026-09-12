# Three-Way Split — Who Builds What

Companion to `PLAN.md`. Read `PLAN.md` Sections 1 and 2 in full, then your own lane below,
then your assigned `4.x` package(s). This file only assigns work; the contracts and the
specs live in `PLAN.md` and it wins any disagreement.

**Verdict: a 3-way parallel split works.** There is a ~10 minute serial prologue at the
start, and integration (Package E) cannot be *finished* in parallel — one lane owns it and
front-loads other work while waiting. Everything else genuinely runs at the same time,
because the three lanes touch disjoint files.

---

## Step 0 — the prologue (~10 min, ONE person, everyone else waits)

`PLAN.md` §3 says the probe "BLOCKS EVERYTHING". That is stricter than necessary for a
three-person team, and this is the correction: **step zero splits in two, and only the
second half blocks anybody.**

**0a. The shared-files commit — needs no credentials, blocks Lanes 2 and 3.** Commit these
straight to `master`, all at once, before anyone branches:

| File | Content |
|---|---|
| `speedrun/types.py` | the §2.1 dataclasses, copied verbatim |
| `speedrun/__init__.py` | empty |
| `conftest.py` | empty (without it `pytest tests/...` cannot import `speedrun`) |
| `.env.example` | `ANTHROPIC_API_KEY=` |
| `requirements.txt` | **complete, all five deps** — see the conflict rule below |
| `tests/fixtures/python_programming_language.html` | the `curl` in §4.A |

**Python version.** The project targets **3.10+**. The macOS system `python3` is still
**3.9.6** — check yours with `python3 --version` and use `python3.11` (or a venv built from
it) if you are on 3.9. `speedrun/types.py` carries `from __future__ import annotations` so
the one module all three lanes import works either way, but your own code will not.

**0b. The Steel probe — needs `steel` auth, blocks Lane 1 only.** This is §3's script and
`docs/steel-json-shapes.md`. It is Lane 1's first task, not a shared prerequisite, because
Lane 1 is the only consumer of the JSON shapes.

So: one person spends ten minutes on 0a, pushes, and all three lanes start.

---

## The three lanes

Pick by taste, with one constraint: **whoever takes Lane 1 should already have `steel`
installed and authenticated**, since Lane 1 runs the probe and is on the critical path.

### Lane 1 — Browser & Loop  (`PLAN.md` §4.B + §4.E)

**Owns:** `speedrun/steel_client.py`, `speedrun/race.py`, `speedrun/cli.py`,
`speedrun/config.py`, `docs/steel-json-shapes.md`, `README.md`

Everything that talks to Steel or drives the race. Order of work:

1. Run the §3 probe. Commit `docs/steel-json-shapes.md`. Post the five answers in chat —
   Lane 2 and Lane 3 do not need them, but the team should see them.
2. `steel_client.py` against the recorded shapes. Hit the §4.B acceptance criteria,
   including timing one full hop and writing the number down.
3. `config.py`, then scaffold `race.py` and `cli.py` against **fakes** for A/C/D — the loop
   in §4.E step 5 is mostly `steel_client` calls, so you can write and test the whole
   structure before anyone else lands.
4. Write `README.md` while waiting for Lanes 2 and 3.
5. Wire up for real at the integration checkpoint.

You are the busiest lane and also the one with the most waiting. Steps 3 and 4 are what
keep you off the blocked list.

### Lane 2 — HTML & Titles  (`PLAN.md` §4.A)

**Owns:** `speedrun/links.py`, `speedrun/wiki.py`, `tests/test_links.py`,
`tests/test_wiki.py`

Pure logic, zero I/O, no credentials, no network. Order of work:

1. The fixture test first — `len(extract_candidates(fixture)) > 200`. Get it **red**, then
   green. This is the single highest-value test in the repo; it is the check that would
   have caught the defect that killed v1.
2. `extract_candidates` per §4.A steps 1–7, then `find_target`.
3. `canonical_title_from_html`, `title_from_url`, `url_from_title`, `titles_match`.
4. The unit fixtures. **Write their hrefs absolute** — a fixture using `/wiki/Foo` agrees
   with a bug instead of catching it.
5. Ship `python -m speedrun.links <file.html>` so the others can eyeball a candidate list.

You are the only lane that can be fully done and verified without any credential. If you
finish early, *offer* to take `README.md` — but Lane 1 owns it until it says so in chat.
An unclaimed handoff is how two people end up editing the same file.

### Lane 3 — Model & Screen  (`PLAN.md` §4.C + §4.D)

**Owns:** `speedrun/picker.py`, `speedrun/display.py`, `tests/test_picker.py`,
`tests/test_display.py`

Everything the LLM and the audience see. No browser dependency at all. Order of work:

1. `display.py` first, and its `python -m speedrun.display` demo mode. It needs nothing
   from anyone, and it gives the team something to look at inside the first hour — which
   matters more than it sounds at a hackathon.
2. `picker.py`: the tool call, the 0-based render, the `visited` filter, `NoCandidatesError`.
3. `tests/test_picker.py`, including the two tests that exist because v1 got them wrong:
   the index-base regression test, and `AuthenticationError` re-raising instead of
   silently falling back.

Read the `link_index` warning in §4.C before you write the render. It is the only
silent-wrong-answer bug in the plan and it is yours to not ship.

---

## Rules that keep this parallel

1. **Only touch files your lane owns.** The lanes are disjoint by design; that is the whole
   reason this works. Need something outside your lane? Ask, don't edit.
2. **`requirements.txt` is committed complete in step 0a** and then nobody edits it:
   `anthropic>=1,<2`, `beautifulsoup4>=4.12`, `rich>=13.7`, `python-dotenv>=1.0`, `pytest`.
   Three people appending dependencies to one file is the most likely merge conflict here,
   and it is entirely avoidable.
3. **`speedrun/types.py` is frozen after step 0a.** If you need a field changed, that is a
   §2 contract amendment: say so in chat, get agreement, amend the log at the top of §2.
   Do not just add the field.
4. **Branch per lane, merge on green.** `lane-1-browser`, `lane-2-html`, `lane-3-model`.
   Don't let a branch live more than an hour or two — long-lived branches with a frozen
   contract are pure downside.
5. **Nobody blocks on Lane 1.** Lanes 2 and 3 need `types.py` and nothing else.

---

## Integration checkpoint

Agree a wall-clock time now — when Lanes 2 and 3 expect to be green. At that point Lane 1
swaps the fakes for the real modules and you run §4.E's three acceptance commands together,
on the projector, with the real Steel session:

```bash
python -m speedrun.cli --start "Python (programming language)" --target "Guido van Rossum"
python -m speedrun.cli --start "Cat" --target "Nuclear weapon"
python -m speedrun.cli --start "Snakes" --target "WWII"          # both endpoints redirect
```

Run 1 proves `find_target` and the win check. Run 3 is the redirect regression — the run
that would have failed on stage under v1. Then Ctrl+C mid-race, and Enter mid-race
(`winner="human"`), each confirming no lingering session via `steel browser sessions`.

**Do this earlier than feels necessary.** The first end-to-end run is where the surprises
are, and every one of the three defects v2 fixed was invisible until real HTML and a real
session were in the loop.

---

## The honest caveat

Package E is integration: it cannot be *finished* until A, C and D exist. The split above
handles that by giving Lane 1 the probe first and the README last, so it has real work at
both ends — but if all three of you are idle-hands types who hate waiting, the alternative
is Lane 1 drops `race.py`/`cli.py` and whoever finishes first picks them up. Decide that
when you get there, not now.

Everything else here is genuinely parallel.
