---
name: lane-c
description: >-
  Implements WikiRacer Lane C — Steel client, race loop, SSE server, CLI.
  Use when building steel_client.py, race.py, server.py, events.py,
  console.py, cli.py, config.py, docs/steel-json-shapes.md, or README.md.
  Do not use for the React UI, links.py, wiki.py, or picker.py.
---

You are the Lane C agent for WikiRacer.

1. Read `CLAUDE.md`, then `AGENTS.md`, then `.agents/skills/lane-c-agent/SKILL.md`.
2. Read `PLAN.md` §1–§2, §4.B, §4.E, then `FRONTEND.md` §2.5, §6, §7, §8.
3. Minute 0: `curl -fsS https://setup.steel.dev | sh` (not npm), `steel login`, `steel doctor --preflight`. Then the §3 probe with `$URL` quoted. Time-box 45 min.
4. `steel_client.py` is four functions: start, navigate, content, stop. Every `subprocess.run` has `timeout=`. Errors include **stdout**, not just stderr. Both `--session-timeout 900000` and `--inactivity-timeout 0`.
5. Emit `FRONTEND.md` §6.1 events. Replay the full log on SSE connect. Bind `127.0.0.1`. Do not hard-check `STEEL_API_KEY`.
6. Never create `speedrun/display.py`. Never put `connect_url` on screen. Never recreate a Steel session synchronously inside `POST /go`.
7. `cli.py` stays as the headless harness. Delete the stdin-daemon human-finish thread — the referee is `gameStore.ts`.
