# WikiRacer — agent entry

Read [`CLAUDE.md`](./CLAUDE.md) first. Then this file. Then **only** your lane skill.

A human races an AI agent on Wikipedia inside one web app. One shared clock. First
canonical title to the target wins. `FRONTEND.md` owns everything user-facing.
`PLAN.md` §2 still owns the Python contracts. **`speedrun/display.py` must not be created.**

## The three lanes — take FRONTEND.md §9, not PLAN.md packages

`PLAN.md` Packages A–E and `ASSIGNMENTS.md` Lanes 1–3 are the **old** split.
`FRONTEND.md` §9 is the current 3-way split. The letters do **not** match:

| Say this | Means this | Does **not** mean |
|---|---|---|
| **Lane A** | Shell, flow, referee (`FRONTEND.md` §9.1) | `PLAN.md` §4.A (that's Lane B now) |
| **Lane B** | Wikipedia renderer + extractor + picker | `ASSIGNMENTS.md` Lane 2 alone |
| **Lane C** | Steel, race loop, SSE server | `PLAN.md` §4.C (picker moved to B) |

This branch is **Lane A**. Skill: [`.agents/skills/lane-a-shell/SKILL.md`](./.agents/skills/lane-a-shell/SKILL.md).

## Branch per lane

| Lane | Branch | Skill | Agent brief |
|---|---|---|---|
| A | `lane-a-shell` | `.agents/skills/lane-a-shell/` | `.claude/agents/lane-a.md` |
| B | `lane-b-wikipedia` | `.agents/skills/lane-b-wikipedia/` | `.claude/agents/lane-b.md` |
| C | `lane-c-agent` | `.agents/skills/lane-c-agent/` | `.claude/agents/lane-c.md` |

Only touch files your lane owns. Importing across lanes is expected; editing across lanes is a chat message, not a commit.

## Read order by task

| Task | Read |
|---|---|
| Setup / Results / chrome / timer / store / wiki API / mock feed | `FRONTEND.md` §0, §3, §4.1–4.2, §4.4, §5.1, §5.4–5.5, §6, §7, §9.1–9.2 |
| Article renderer / `links.ts` / `links.py` / picker | `FRONTEND.md` §5 + `PLAN.md` §4.A and §4.C |
| Steel / `race.py` / `server.py` | `PLAN.md` §1–§2, §4.B, §4.E → `FRONTEND.md` §6 and §8 |

## Frozen after prologue — do not edit

`speedrun/types.py`, `speedrun/__init__.py`, `conftest.py`, `requirements.txt`, `.env.example`, `tests/fixtures/*`, and (once pushed) `web/{package.json,vite.config.ts,tsconfig*,index.html}`, `web/src/styles/theme.css`, `web/src/agent/types.ts`.
