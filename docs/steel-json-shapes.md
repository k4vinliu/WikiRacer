# Steel CLI — recorded output shapes

**Lane C. Recorded 2026-09-12** against **`steel 0.4.4`** (the native binary at
`~/.steel/bin/steel`), cloud mode, region `us-east`. This is the probe from `PLAN.md` §3 as
amended by `FRONTEND.md` §8 (Q3 deleted, Q6 and Q7 added), plus the hop timing `PLAN.md`
§4.B asks for.

Re-check after any Steel upgrade with `python3.11 -m speedrun.steel_client`, the §4.B smoke test. It
spends one short session, parses every shape our code depends on from the live CLI, and fails loudly
if one has drifted. The CLI does drift, and the vendored reference in `.agents/skills/steel-browser/`
is already wrong about the one field that matters most (Q1).

**Measured end to end through `speedrun.server`, same day** (dev picker, so no LLM time in these):
`POST /race` answers in 1 ms. Arming (cold start + `sessions get` + the title check + parking on the
start article) reaches `ready` in **3.87 s**, against the frontend's 20 s budget. A `find_target` hop on
*Python (programming language)*: `thinking` at 287 ms after GO, `arrive` at 838 ms, `done` at
1,469 ms. Headless dev-picker hops run 0.5–0.8 s each. When a stream was dropped mid-race, the server
released the session by itself 6.4 s later.

Every JSON sample below is verbatim stdout, with `token=` / `apiKey=` values redacted.

---

## The answers

| # | Question | Answer — verified |
|---|---|---|
| **Q1** | Live-view key, session id, granted timeout | The key is **`liveUrl`** (camelCase). **Not** `live_url` — `steel-browser-lifecycle.md:63` documents the *human* output, and `FRONTEND.md` §8 relied on it. `id` is a UUID. The start output has no `timeout`; it has `remainingMs` (`899002`). `steel sessions get <id>` reports `"timeout": 900000`. **And `liveUrl` is the wrong URL to embed — see Q7.** |
| **Q2** | `content` / `get url` envelope | `{"data": "<string>", "success": true}`. `data` is the bare string. `content` on *Python (programming language)*: **1,287,490 bytes of HTML inside 1,335,241 bytes of stdout**, 577 ms. |
| Q3 | *(deleted by `FRONTEND.md` §8)* | — |
| **Q4** | Where do errors go? | **stdout, as JSON, exit code 1.** stderr is empty (0 bytes). `{"error":"Wait timed out after 3000ms","error_code":"internal_error","success":false}` |
| **Q5** | Does `wait -u` honour `--timeout`? | Yes. `--timeout 3000` → 3,167 ms wall, exit 1. (Moot: `wait_for_url` is cut by `FRONTEND.md` §0.) |
| **Q6** | Cold `browser start` | **1,399 / 1,862 / 1,156 ms** across three sessions. Well inside the 20 s arming budget. |
| **Q7** | Does the live view frame? | `liveUrl` = `https://app.steel.dev/sessions/<id>` is the **Steel dashboard**: a 1,602-byte Vercel SPA shell titled *"Steel \| Open-source Headless Browser API"* that needs a Steel login. Useless on a projector. **The frameable player is `debugUrl` from `steel sessions get <id>`:** `https://api.steel.dev/v1/sessions/<id>/player` → HTTP 200, `text/html`, 65,910 B, `<title>Steel Session Player (WebRTC)`, **no `x-frame-options`, no `content-security-policy`**. `?interactive=false` is templated in server-side (`const interactive = 'false' === 'true';`) and `?hideOverlay=true` is documented in the page's own comments. `theme=` and `showControls`: 0 occurrences (`FRONTEND.md` §2.5 was right). |
| **4.B** | One full hop | `navigate --wait-until domcontentloaded` then `content`: **1,030 / 1,013 / 1,168 ms — median 1.03 s** (navigate 680–831 ms, content 211–349 ms). The 3.5 s budget in `PLAN.md` §4.E has ~2.4 s of headroom for the LLM call. |

**What `steel_client.start_session()` therefore does:** parses `id`/`name`/`remainingMs` from
`browser start`, then reads `debugUrl` and `timeout` from `steel sessions get <id>` (+~250 ms,
paid once, at arming) and hands the frontend
`https://api.steel.dev/v1/sessions/<id>/player?interactive=false&hideOverlay=true` as
`SessionHandle.live_url`. If `sessions get` fails it builds that URL from the id — the scheme was
verified above.

---

## Traps found (no document mentions any of these)

1. **A command against an unknown session name silently STARTS A NEW SESSION.**
   `steel browser get url --session no-such-session-1789253478 --json` → **exit 0**,
   `{"data":"about:blank","success":true}`, 1.56 s (that is a cold start), and the later
   `steel browser stop` for that name reported stopping it. A typo'd, expired or
   already-stopped name therefore never errors: the next `navigate` drives a fresh, invisible
   browser while the projector shows the dead one. `steel_client` / `race.SteelSource` defend
   in three places:
   - never send a command to a session past its lifetime (`SteelSource._guard`);
   - `content()` treats a page under 1 KB as `SteelSessionLost` (no Wikipedia article is that small);
   - only the thread that owns a session ever stops it, *after its last command*, and every
     `close()` re-sends the idempotent stop by name — so a session re-created by a stray
     command is still torn down.
2. **`liveUrl` is the dashboard, not the player** (Q7). The same dashboard URL appears under
   three names: `liveUrl` (`browser start`), `viewerUrl` (`browser sessions`),
   `sessionViewerUrl` (`sessions get`). The player is only in `debugUrl`.
3. **The npm package is a shim.** `@steel-dev/cli` 0.3.1 on npm spawns `~/.steel/bin/steel`.
   Median `--version` round trip: **25 ms through the shim vs 3 ms direct**. `steel_client`
   calls the native binary directly (override with `STEEL_BIN=/path/to/steel`).
4. **`content` returns the live DOM after Wikipedia's JS has run** (`<html class="client-js …">`,
   5 `<script>` tags), not the server HTML. Lane B's extractor finds **324** legal moves in it on
   *Python (programming language)* vs **325** in the curl'd fixture.
5. **Wikipedia rewrites the URL after a redirect.** Navigating to `/wiki/GVR_(disambiguation)`
   (an `mw-redirect` link) reported `"url":"https://en.wikipedia.org/wiki/GVR"`, and the canonical
   title in the HTML was `GVR`. Nothing may derive a title from a URL.
6. **Two concurrent sessions work.** No concurrency limit at 2; concurrent navigates took 962 /
   1,552 ms.
7. **python.org's Python 3.13 on macOS ships no CA bundle** (`ssl.get_default_verify_paths()`
   → `cafile=None, capath=None`), so `urllib` fails every HTTPS request with
   `CERTIFICATE_VERIFY_FAILED`. `speedrun/race.py` falls back to `/etc/ssl/cert.pem`. Not
   Steel, but this probe found it.
8. **A missing Wikipedia article looks like a real page in HTML.** The read view of
   `/wiki/NotARealArticleXyzzy` is HTTP 404 with a `noarticletext` marker — **and a
   `<link rel="canonical">` that repeats the typo**. Via Steel (which reports no status code),
   `canonical_title_from_html` would "resolve" a typo to itself. So race endpoints are validated
   with `action=query&redirects=1`, which says `"missing": true`.

---

## Raw shapes

### `steel browser start --session <name> --session-timeout 900000 --inactivity-timeout 0 --json`

exit 0, 1,399 ms, stderr empty.

```json
{
  "data": {
    "connectUrl": "wss://connect.steel.dev/?sessionId=4d04be8b-4e00-8022-b8fd-fad0b6aaae10&token=<redacted>&apiKey=<redacted>",
    "id": "4d04be8b-4e00-8022-b8fd-fad0b6aaae10",
    "liveUrl": "https://app.steel.dev/sessions/4d04be8b-4e00-8022-b8fd-fad0b6aaae10",
    "mode": "cloud",
    "name": "probe-1789253478",
    "remainingMs": 899002
  },
  "success": true
}
```

`connectUrl` carries credentials. Never log it, never put it on screen (`FRONTEND.md` §2.5).

### `steel sessions get <id> --json`

exit 0, 270 ms. (`websocketUrl` token redacted.)

```json
{"data":{"browserMode":"standard","createdAt":"2026-09-12T22:51:18.863Z","creditsUsed":0,
"debugConfig":{"interactive":true,"systemCursor":true},
"debugUrl":"https://api.steel.dev/v1/sessions/4d04be8b-4e00-8022-b8fd-fad0b6aaae10/player",
"deviceConfig":{"device":"desktop"},"dimensions":{"height":1080,"width":1920},"duration":1281,
"eventCount":0,"fullscreen":false,"headless":false,"id":"4d04be8b-4e00-8022-b8fd-fad0b6aaae10",
"isSelenium":false,"optimizeBandwidth":{},"persistProfile":false,"projectId":"d002fe5e-…",
"proxyBytesUsed":0,"proxySource":null,"region":"us-east","releaseReason":null,
"sessionViewerUrl":"https://app.steel.dev/sessions/4d04be8b-4e00-8022-b8fd-fad0b6aaae10",
"solveCaptcha":false,"status":"live","stealthConfig":{},"timeout":900000,
"userAgent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
"websocketUrl":"wss://connect.steel.dev?sessionId=…&token=<redacted>"},"success":true}
```

After `stop`: `"status":"released","releaseReason":"user_requested"`. Note
`debugConfig.interactive: true` — the session's own default *is* interactive, which is why the
player URL must carry `?interactive=false`.

### `steel browser navigate <url> --session <name> --wait-until domcontentloaded --json`

exit 0, 680–1,135 ms. The URL was passed as a single argv element; the v1 probe died here on an
unquoted `(`.

```json
{"data":{"title":"Python (programming language) - Wikipedia","url":"https://en.wikipedia.org/wiki/Python_(programming_language)"},"success":true}
```

### `steel browser get url --session <name> --json`

exit 0, 228 ms.

```json
{"data":"https://en.wikipedia.org/wiki/Python_(programming_language)","success":true}
```

### `steel browser content --session <name> --json`

exit 0, 577 ms first read, 211–349 ms after. First 300 characters of stdout:

```text
{"data":"<html class=\"client-js vector-feature-language-in-header-enabled vector-feature-language-in-main-menu-disabled vector-feature-language-in-main-page-header-disabled vector-feature-page-tools-pinned-disabled vector-feature-toc-pinned-clientpref-1 vector-feature-main-menu-pinned-disabled vect
```

Contents of `data` on *Python (programming language)*: `<link rel="canonical">` present; hrefs
**1,054** absolute `https://en.wikipedia.org/wiki/`, **66** `/wiki/` (chrome), **48** `./`.
`canonical_title_from_html` → `Python (programming language)`.

### Error envelope (any command) — stdout, exit 1

```json
{"error":"Wait timed out after 3000ms","error_code":"internal_error","success":false}
```

### `steel browser wait -u <substring> --session <name> --timeout 5000 --json` (success)

```json
{"data":{"url":"Python","waited":"url"},"success":true}
```

### `steel browser stop --session <name> --json` — twice

Both exit 0, ~300 ms. Idempotent:

```json
{"data":{"stoppedSessions":["probe-1789253478"]},"success":true}
```

### `steel browser sessions --json`

While a session is live (91 ms):

```json
{"data":[{"id":"4d04beae-0f60-801e-8e62-6c9f318f27e2","mode":"cloud","name":"probe3-1789253763","status":"live","viewerUrl":"https://app.steel.dev/sessions/4d04beae-0f60-801e-8e62-6c9f318f27e2"}],"success":true}
```

After every stop: `{"data":[],"success":true}`.

### `steel sessions release [SESSION_ID]` — help only

`Release a cloud session`. Takes the cloud id positionally, or `--session <name>` to resolve it
from a local daemon name; `-a/--all` releases everything. `stop_session()` falls back to this
by id if the named stop fails.

### `steel doctor --preflight --json`

exit 0, ~270 ms:

```json
{"data":{"checks":[{"category":"auth","detail":{"key":"ste-<redacted>","source":"config"},"name":"API key configured (source: config)","status":"pass","transient":false},{"category":"auth","name":"API key valid","status":"pass","transient":false},{"category":"api","detail":{"latency_ms":177,"mode":"cloud","url":"https://api.steel.dev/v1"},"name":"https://api.steel.dev/v1 reachable (177ms)","status":"pass","transient":false}],"overall":"pass"},"success":true}
```

### `steel browser batch` — help only

`steel browser batch [--bail] --session <name> "<cmd>" "<cmd>" …` runs several commands in one
invocation. It's the `PLAN.md` §4.E latency lever. Not built: at a 1.03 s median hop there's
nothing to buy back.

---

## The player page (Q7 detail)

`GET https://api.steel.dev/v1/sessions/<id>/player?interactive=false&hideOverlay=true` →
HTTP 200, 65,172 B, `content-type: text/html; charset=utf-8`, no frame-blocking headers. From
the page source:

```text
const interactive = 'false' === 'true';        // ?interactive=false, templated server-side
//   - ?hideOverlay=true          - Start with overlay hidden (use your own loa…
```

Transport is WebRTC. The `live_url` in the `ready` event is exactly this URL.
