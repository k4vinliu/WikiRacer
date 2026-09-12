---
name: lane-c-agent
description: >-
  Implements WikiRacer Lane C — Steel browser client, race loop, SSE server,
  CLI, config, README. Use when building steel_client.py, race.py, server.py,
  events.py, console.py, cli.py, config.py, or docs/steel-json-shapes.md.
---

# Lane C — Agent & Bridge

You own everything that talks to Steel or drives the agent loop, plus the tiny
stdio server the frontend subscribes to. You do **not** own the React UI,
`links.py`, or `picker.py`.

Picker ownership moved to Lane B. `display.py` is deleted — use `console.py`
(one stderr line per event) for your own debugging.

## Read first

`CLAUDE.md` → `AGENTS.md` → `PLAN.md` §1–§2, §2.3 traps, §3 probe, §4.B, §4.E → `FRONTEND.md` §2.5, §2.6, §6, §7, §8, §9.2.

## Own these files — only these

```
speedrun/steel_client.py
speedrun/race.py
speedrun/server.py
speedrun/events.py
speedrun/console.py
speedrun/cli.py
speedrun/config.py
docs/steel-json-shapes.md
README.md
```

`README.md` last, and only reassignable at CP4.

## Do not create

`speedrun/display.py`, `tests/test_display.py`. Do not edit Lane A/B files.

## Order of work

1. **Minute 0, before the frontend prologue matters to you:** native installer `curl -fsS https://setup.steel.dev | sh` — **not** `npm i -g @steel-dev/cli`. `steel login`. `steel doctor --preflight`.
2. `PLAN.md` §3 probe with `$URL` quoted. Time-box **45 min**. Record answers in `docs/steel-json-shapes.md`, including new Q6 (time `browser start` cold) and Q7 (`curl -I "$LIVE_URL"` — no `x-frame-options`).
3. `steel_client.py` — four functions: `start_session`, `navigate`, `content`, `stop_session`. Arrival is detected by canonical title, not URL. Every `subprocess.run` has `timeout=`. Parse `--json`. Errors include **stdout**.
4. `config.py` → `events.py` → `server.py` → `race.py` → `console.py` + `cli.py` → `README.md`.

## Steel traps (verified the hard way)

1. **`--session-timeout 900000` AND `--inactivity-timeout 0`.** Independent. `timeout` defaults to 5 minutes, create-time only, and is what kills a live race. Prewarming starts that clock at Setup, so inactivity-timeout 0 is now routine (trap 4 in `FRONTEND.md` §8).
2. Re-prewarm on a background timer at 0.8× and re-emit `ready`. **Never** recreate a session synchronously inside `POST /go`.
3. `content` / `get url` return a string inside an envelope. Use the probe record, not a guessed field name.
4. `live_url` is the projector/iframe URL. **Never put `connect_url` on screen.** Embed with `?interactive=false`.
5. Use `python3.11`, not `python3`.

## Server (`FRONTEND.md` §2.3, §7)

Stdlib `ThreadingHTTPServer` on `127.0.0.1:8848`. Zero new dependencies.

- `POST /race` — start a run, prewarm Steel
- `POST /race/{id}/go` — the gun (both clocks start)
- `GET /events` — SSE, **replay the full log on connect** (load-bearing; without it arming hangs)
- `POST /stop` — kill run + Steel session
- `GET /health` — `{ok, anthropic_key, steel}`

Headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Access-Control-Allow-Origin: *`.

Emit `FRONTEND.md` §6.1 events via an `emit` callback. `anchor_text` is required on `pick`.

## `config.py`

- Load `.env` (`python-dotenv`).
- Require `ANTHROPIC_API_KEY`; construct `anthropic.Anthropic(timeout=8.0, max_retries=1)`.
- **Do not hard-check `STEEL_API_KEY`.** Run `steel doctor --preflight`.
- Defaults: `claude-haiku-4-5`, `max_hops=25`, `session_timeout_ms=900_000`.

## `race.py` / `cli.py`

`cli.py` stays as the headless agent-only path. **Delete the stdin-daemon human-finish thread** — the referee is `gameStore.ts`. Keep `KeyboardInterrupt` cleanup.

`try/finally` always `stop_session`. A leaked Steel session is the one unacceptable outcome.

`NoCandidatesError` → `RaceResult(reason="dead_end")`. Win check is `canonical_title_from_html`, not the URL. Bot moves with `navigate(candidate.href)`.

## Probe questions to write down

1. `live_url` vs `liveUrl`; session `id`; granted timeout.
2. `content` envelope + first ~300 chars + byte length.
3. Errors: stdout or stderr? Exit code?
4. Does `wait -u` honour `--timeout`?
5. Time one full hop (`navigate` → content). Time `browser start` cold (Q6).
6. `curl -I "$LIVE_URL"` — confirm no `x-frame-options` (Q7).
