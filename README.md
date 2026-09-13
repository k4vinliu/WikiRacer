# WikiRacer

**A human races an AI agent across Wikipedia, in one web app, on one shared clock.**

## What you will see when this works

You pick a difficulty and press **Start Race**. For a few seconds the app *arms*: your start
article loads in the left panel, and on the right a real Chrome in Steel's cloud boots and
parks on the same article. That browser is the live view you watch. Then 3-2-1-GO. You click
links in the article body on the left. The agent (Claude, choosing from exactly the same legal
links) drives its own browser on the right, and its reasoning log names every link it clicked,
as the text appeared on the page, and why. The first to land on the target article wins. It's
judged by *canonical title*, so redirects count. The clock stops, and Results shows both paths.

No keys? The app still plays end to end against a scripted mock agent. That's the stage fallback.

---

## Quick start: mock agent, no keys, no Python

```bash
npm --prefix web install
npm run dev                       # from the repo root → http://127.0.0.1:5173
```

## Racing the real agent

**Prerequisites**

| Need | How |
|---|---|
| Python **3.10+** | `python3.11 --version`. macOS's system `python3` may be 3.9, which can't import this code (`X \| None` annotations). Any 3.10+ interpreter works. |
| Node 18+ | `node --version` |
| Steel CLI, logged in | `curl -fsS https://setup.steel.dev \| sh` (the **native** installer, not `npm i -g @steel-dev/cli`, which is now just a slower shim), then `steel login`, then `steel doctor --preflight` |
| An Anthropic API key | goes in `.env` (below). **Not** a Steel key: `steel login` handles Steel. |

**Once**

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # then paste your key after ANTHROPIC_API_KEY=
npm --prefix web install
```

**Every time**: two terminals.

```bash
# terminal 1: the agent server (127.0.0.1:8848). Ctrl+C releases the Steel session.
source .venv/bin/activate
python -m speedrun.server

# terminal 2: the app
npm --prefix web run dev
```

Open **http://localhost:5173/?agent=real**. Without `?agent=real` the app uses the mock agent.

The server prints one line per agent event, and checks your Anthropic key and Steel login at
startup. If either is wrong it still starts, and a race shows the reason on screen instead of
hanging.

| Server flag | What it's for |
|---|---|
| `--page-source http` | No browser: the agent reads Wikipedia over HTTPS. Same loop, same extractor, same LLM, but no live view. The fallback if Steel is down (`FRONTEND.md` §9.3). |
| `--picker first` | **Dev only.** Always takes the first unvisited link, and needs no API key. It exercises Steel, the loop and the event stream. It will not reach your target. |

## The headless agent (Lane C's regression harness)

The same loop, in a terminal, with no app:

```bash
python -m speedrun.cli --start "Python (programming language)" --target "Guido van Rossum"
python -m speedrun.cli --start "Cat" --target "Nuclear weapon"
python -m speedrun.cli --start "Snakes" --target "WWII"      # both ends are redirects: must pass
steel browser sessions                                          # must list nothing afterwards
```

`--difficulty easy|medium|hard`, `--max-hops N`, `--model`, `--page-source http` and
`--picker first` all work here too. Exit code: 0 if the agent won, 1 if it didn't, 2 for a
setup problem, 130 after Ctrl+C. Ctrl+C still releases the browser.

## Tests

```bash
python -m pytest                    # all offline: no keys, no network, no Steel
npm --prefix web run test
python -m speedrun.steel_client     # live Steel smoke test: spends one short session
```

## On the demo machine

- Chrome, fullscreen, **1920×1080 at 100% zoom**. The Race screen is laid out for exactly that.
- A **mouse and keyboard for the human racer.** The presenter is the player.
- On venue wifi, the moment you arrive. If any of these isn't `200`, tether to a phone:

  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' 'https://en.wikipedia.org/w/api.php?action=parse&page=Cat&prop=text&format=json&origin=*'
  curl -s -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org/
  curl -s -o /dev/null -w '%{http_code}\n' 'https://fonts.googleapis.com/css2?family=Inter'
  ```
- Run one full race before the audience arrives, then check `steel browser sessions` is empty.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The agent panel says *Agent disconnected* | The server isn't running, or it was restarted mid-race. Start `python -m speedrun.server`. |
| Arming times out (20 s) | Steel is slow or down. Check `steel doctor --preflight`, or restart the server with `--page-source http`. |
| *Anthropic rejected the API key* / *ANTHROPIC_API_KEY is not set* | Fix `.env`, then restart the server. |
| *speedrun/picker.py isn't in this checkout* | Lane B's picker isn't merged into your branch yet. Pull it, or use `--picker first` to test the rest. |
| The agent seems to hang | `steel browser sessions`, then `steel browser stop --all`. The server also stops leftover `wikiracer-srv-*` sessions every time it starts. |
| A session died mid-race | Almost certainly its `--session-timeout`, which is create-time only and defaults to 5 minutes. We always pass 15 minutes. |
| `CERTIFICATE_VERIFY_FAILED` | python.org's macOS Python ships no CA bundle. The agent already falls back to `/etc/ssl/cert.pem`. For your own scripts, run *Install Certificates.command* in `/Applications/Python 3.x/`. |
| Wikipedia HTTP 429 | Rate-limited. Slow down, then retry in a minute. The agent retries a page load once, then stops cleanly. |

## The agent server protocol

This is for anyone touching `web/src/agent/sseFeed.ts`. The server is standard library only
and listens on `127.0.0.1` only. Only pages served from this machine may drive it, because a
race spends Steel and Anthropic credit.

| Request | Answer |
|---|---|
| `POST /race` `{start, target, difficulty?, find_target?, max_hops?}` | `201 {id, events}` at once. Arming runs in the background and ends in a `ready` event. A new race stops the previous one. |
| `GET /events?race=<id>` (`<id>` may be `current`) | Server-Sent Events. Replays the race's whole log, then streams it live. Plain `message` frames with `id:` = `seq`; `Last-Event-ID` resumes. |
| `POST /race/<id>/go` | The gun: the server's clock starts when this arrives. `409` until `ready`. |
| `POST /stop` | Stops the current race and releases its browser. Idempotent. |
| `GET /health` | `{ok, anthropic_key, steel, detail, race, …}` |

Events are the §6.1 schema: `web/src/agent/types.ts` on one side, `speedrun/events.py` on the
other, and `tests/test_events.py` fails the build if they drift apart. `at` is milliseconds
since the gun (0 before it). An `arrive` is stamped when the agent's page finished loading.
Every race except one stopped by the client ends with exactly one `done`. If a race's event
stream drops (a reload, a closed tab), the server stops that race and releases its browser
within about 6 seconds (`FRONTEND.md` §2.7; measured 6.4 s).

## Deploying the app (Vercel)

**What deploys is the frontend only, and it plays against the MOCK agent.** That is the
stage fallback: the whole experience -- countdown, clicking, win detection, Results -- with a
scripted opponent instead of a real browser. Good for a shareable link; not what judges
should watch.

**The Python server cannot go on Vercel**, and this is architectural, not a config you can
fix. `speedrun/server.py` keeps the `RaceManager`, the `EventLog`, the Steel session and the
`go` event in process memory, and `POST /race` -> `GET /events` -> `POST /race/<id>/go` are
three separate requests that must share all of it. Serverless invocations are stateless and
may land on different instances, so the sequence breaks. The agent also shells out to the
`steel` NATIVE BINARY, whose credentials come from `steel login` writing a config file (we
never read `STEEL_API_KEY` -- `PLAN.md` §4.E). A real agent needs a host with long-lived
processes: Railway, Render, Fly.

### Auto-deploy on push

1. vercel.com/new -> import `kieran-ym/WikiRacer`.
2. **Set Root Directory to `web`.** This is the one that bites: there is no `package.json` at
   the repo root, so a default import fails the build. Everything else is already in
   `web/vercel.json` (vite, `dist`, SPA rewrite).
3. Deploy.

After that, a push to `master` redeploys production and every PR gets its own preview URL.

| Env var | When you need it |
|---|---|
| `VITE_AGENT_BASE` | Only if you host the Python server somewhere. Points the app at it; unset, it uses `http://127.0.0.1:8848` and the local two-terminal setup is unchanged. It is a URL, **never a secret** -- anything `VITE_`-prefixed is inlined into the public bundle, which is why the API keys stay server-side. |

For a throwaway link with no account, `npm --prefix web exec vercel deploy --temporary`
prints a URL that lives 60 minutes and a link to claim it.

## Where things are

| | |
|---|---|
| `CLAUDE.md` → `AGENTS.md` → `FRONTEND.md` | Read these first, in that order. `FRONTEND.md` owns everything user-facing, and `PLAN.md` §2 owns the Python contracts. |
| `web/` | The app (Lanes A and B). |
| `speedrun/links.py`, `wiki.py`, `picker.py` | The game rule, titles, and the Claude link picker (Lane B). |
| `speedrun/steel_client.py`, `race.py`, `server.py`, `events.py`, `config.py`, `cli.py`, `console.py` | Steel, the race loop, and the bridge to the app (Lane C). |
| `docs/steel-json-shapes.md` | What the Steel CLI really prints, and the traps it hides. Read it before changing a Steel field name. |

**Design note:** the project was inspired by dialed.gg, but our twelve palette tokens and
Fraunces/Inter are an original adaptation. dialed.gg is a white, near-black-card, all-grotesque
site with no serif at all. Don't "correct" our design against it.
