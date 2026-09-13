"""The only module that talks to Steel. Lane C. PLAN.md §4.B, narrowed by FRONTEND.md §0.

Every output shape parsed here was VERIFIED by the probe on 2026-09-12. Read
docs/steel-json-shapes.md before changing a field name. Three facts from it shape this file:

1. Errors print to STDOUT as {"error": ..., "success": false} with exit 1, and stderr is
   empty. So every exception here quotes stdout.
2. `browser start` returns `liveUrl`, and it is the Steel DASHBOARD (needs a login), not the
   frameable player. The player URL is `debugUrl` from `steel sessions get <id>`.
3. A command naming a session Steel no longer knows silently STARTS A NEW ONE on
   about:blank, and exits 0. So: never reuse a name, never talk to an expired session, and
   treat an empty page as a lost session.

Every subprocess.run has a timeout (CLAUDE.md rule 8). A hung CLI raises SteelTimeout, so
the race can tell "Steel is wedged" from "the page did not change".

`python -m speedrun.steel_client` is the PLAN.md §4.B smoke test. It spends one real session.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from speedrun.types import SessionHandle

DEFAULT_TIMEOUT_S = 20.0
CONTENT_TIMEOUT_S = 45.0  # `content` moves ~1.3 MB of JSON through a pipe
START_TIMEOUT_S = 45.0

# Read-only (the audience must not be able to drive the agent's browser), and no loading
# overlay. Both verified in the player page; `theme` / `showControls` do NOT exist.
PLAYER_PARAMS = {"interactive": "false", "hideOverlay": "true"}
PLAYER_URL = "https://api.steel.dev/v1/sessions/{id}/player"
MIN_PAGE_CHARS = 1024  # no Wikipedia article is smaller; about:blank is ~40 characters
INSTALL_HINT = ("Install the native binary with `curl -fsS https://setup.steel.dev | sh`, "
                "then run `steel login`.")


class SteelError(RuntimeError):
    def __init__(self, message: str, *, argv: list[str] | None = None,
                 exit_code: int | None = None, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.argv, self.exit_code, self.stdout, self.stderr = argv, exit_code, stdout, stderr


class SteelTimeout(SteelError):
    """The CLI did not answer in time: Steel is wedged, not the page."""


class SteelNotInstalled(SteelError):
    """There is no `steel` binary to run."""


class SteelSessionLost(SteelError):
    """Our session is gone, and Steel may have started a fresh one under its name."""


def native_bin() -> Path:
    return Path.home() / ".steel" / "bin" / "steel"


def steel_bin() -> str:
    """`STEEL_BIN`, else the native binary, else whatever `steel` is on PATH."""
    override = os.environ.get("STEEL_BIN")
    if override:
        return override
    native = native_bin()
    if native.is_file() and os.access(native, os.X_OK):
        return str(native)  # 3 ms per call, vs 25 ms through the npm shim (probe trap 3)
    found = shutil.which("steel")
    if found:
        return found
    raise SteelNotInstalled(f"The `steel` CLI is not installed. {INSTALL_HINT}")


def _text(b: str | bytes | None) -> str:
    if b is None:
        return ""
    return b.decode("utf-8", errors="replace") if isinstance(b, bytes) else b


def run(args: list[str], timeout: float = DEFAULT_TIMEOUT_S):
    """Run `steel <args> --json` and return the envelope's `data`. Raises SteelError."""
    argv = [steel_bin(), *args, "--json"]
    shown = "steel " + " ".join(args)
    try:
        proc = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise SteelTimeout(f"`{shown}` did not answer within {timeout:g}s", argv=argv,
                           stdout=_text(e.stdout), stderr=_text(e.stderr)) from None
    except OSError as e:
        raise SteelNotInstalled(f"Could not run {argv[0]!r} ({e}). {INSTALL_HINT}", argv=argv) from None
    stdout = proc.stdout or ""
    try:
        envelope = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        envelope = None
    if proc.returncode != 0 or not isinstance(envelope, dict) or envelope.get("success") is not True:
        detail = envelope.get("error") if isinstance(envelope, dict) else None
        detail = detail or stdout.strip()[:500] or (proc.stderr or "").strip()[:500] or "no output"
        raise SteelError(f"`{shown}` failed (exit {proc.returncode}): {detail}", argv=argv,
                         exit_code=proc.returncode, stdout=stdout, stderr=proc.stderr or "")
    return envelope.get("data")


def new_session_name(prefix: str = "wikiracer") -> str:
    """`browser start` ATTACHES to an existing name, so a name must never repeat."""
    return f"{prefix}-{int(time.time())}-{secrets.token_hex(4)}"


def player_url(url: str) -> str:
    """The frameable, read-only live view: `url` plus PLAYER_PARAMS."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update(PLAYER_PARAMS)
    return urlunsplit(parts._replace(query=urlencode(query)))


def _stop_quietly(name: str) -> None:
    try:
        stop_session(name)
    except SteelError:
        pass


def start_session(session_timeout_ms: int = 900_000, inactivity_timeout_ms: int = 0, *,
                  name_prefix: str = "wikiracer") -> SessionHandle:
    """Create a cloud browser, passing BOTH timeouts every time (CLAUDE.md rule 4).

    `--session-timeout` is the lifetime cap. It is create-time only and defaults to 5
    minutes, and it's what kills a live race. `--inactivity-timeout 0` switches off the
    2-minute idle reaper that would otherwise fire during crowd commentary.
    """
    name = new_session_name(name_prefix)
    try:
        data = run(["browser", "start", "--session", name,
                    "--session-timeout", str(int(session_timeout_ms)),
                    "--inactivity-timeout", str(int(inactivity_timeout_ms))], timeout=START_TIMEOUT_S)
    except SteelError:
        _stop_quietly(name)  # a start that timed out may still have created the session
        raise
    sid = data.get("id") if isinstance(data, dict) else None
    if not sid:
        _stop_quietly(name)
        raise SteelError(f"`steel browser start` returned no session id: {data!r}")
    granted = data.get("remainingMs")
    debug_url = None
    try:
        info = session_info(sid)
        debug_url = info.get("debugUrl")
        granted = info.get("timeout") or granted
    except SteelError:
        pass  # the player URL scheme was verified; build it from the id below
    return SessionHandle(
        id=sid,
        name=data.get("name") or name,
        live_url=player_url(debug_url or PLAYER_URL.format(id=sid)),
        session_timeout_ms=int(granted or session_timeout_ms),
    )


def session_info(session_id: str) -> dict:
    """The cloud-side record: debugUrl (the player), timeout, status, ..."""
    data = run(["sessions", "get", session_id])
    if not isinstance(data, dict):
        raise SteelError(f"`steel sessions get` returned {type(data).__name__}, not a session record")
    return data


def navigate(session_name: str, url: str, wait_until: str = "domcontentloaded") -> dict:
    """Move the agent. Returns Steel's {title, url} for logging. The URL is never a title
    source: Wikipedia rewrites it on redirects (probe trap 5). `domcontentloaded`, not
    `networkidle`, because nothing we read depends on the network going quiet."""
    data = run(["browser", "navigate", url, "--session", session_name, "--wait-until", wait_until])
    return data if isinstance(data, dict) else {}


def content(session_name: str) -> str:
    """The page's HTML: the live DOM of Wikipedia's read view. The single source of truth."""
    data = run(["browser", "content", "--session", session_name], timeout=CONTENT_TIMEOUT_S)
    if not isinstance(data, str):
        raise SteelError(f"`steel browser content` returned {type(data).__name__}, not the page HTML")
    if len(data) < MIN_PAGE_CHARS:
        raise SteelSessionLost(
            f"Steel returned a {len(data)}-character page for {session_name!r}: almost certainly "
            "about:blank in a session Steel silently re-created because ours is gone "
            "(docs/steel-json-shapes.md, trap 1).")
    return data


def get_url(session_name: str) -> str:
    """Diagnostics only. Never the win check (PLAN.md §2.3 trap 3)."""
    data = run(["browser", "get", "url", "--session", session_name])
    return data if isinstance(data, str) else ""


def stop_session(session_name: str, session_id: str | None = None) -> None:
    """Stop a session. Idempotent: stopping twice succeeds both times (verified).

    If the named stop fails and we know the cloud id, fall back to releasing it by id. A
    leaked session is the one unacceptable outcome (FRONTEND.md §2.7).
    """
    try:
        run(["browser", "stop", "--session", session_name])
        return
    except SteelError as first:
        if not session_id:
            raise
        try:
            run(["sessions", "release", session_id])
            return
        except SteelError as second:
            raise SteelError(
                f"Could not stop Steel session {session_name!r} ({session_id}): {first}; "
                f"releasing it by id also failed: {second}. Check `steel browser sessions`.") from second


def list_sessions() -> list[dict]:
    """This machine's live named sessions: [{id, mode, name, status, viewerUrl}, ...]."""
    data = run(["browser", "sessions"])
    return [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []


def stop_leaked(prefix: str) -> list[str]:
    """Stop live sessions named `<prefix>-...`, left behind by a crashed earlier run of ours.
    Leaves every other session alone. Returns the names it stopped."""
    stopped = []
    for s in list_sessions():
        name = s.get("name") or ""
        if not name.startswith(prefix + "-"):
            continue
        try:
            stop_session(name, session_id=s.get("id"))
            stopped.append(name)
        except SteelError as e:
            print(f"[steel] could not stop leaked session {name}: {e}", file=sys.stderr)
    return stopped


def doctor() -> tuple[bool, str]:
    """`steel doctor --preflight`: (ok, one line for the host)."""
    try:
        data = run(["doctor", "--preflight"], timeout=30.0)
    except SteelError as e:
        return False, str(e)
    if not isinstance(data, dict):
        return False, f"unexpected `steel doctor` output: {data!r}"
    if data.get("overall") == "pass":
        return True, "steel doctor --preflight: pass"
    failing = [c.get("name", "?") for c in data.get("checks", []) if c.get("status") != "pass"]
    return False, "steel doctor --preflight failed: " + (", ".join(failing) or str(data.get("overall")))


def _smoke() -> int:
    """PLAN.md §4.B acceptance: start → navigate → get url → content → navigate to an href
    the extractor found → canonical title changed → stop → stop again → nothing left."""
    start_url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
    t = time.perf_counter()
    h = start_session(name_prefix="wikiracer-smoke")
    print(f"started {h.name} ({h.id}) in {time.perf_counter() - t:.2f}s, "
          f"granted {h.session_timeout_ms} ms\n  live view: {h.live_url}")
    try:
        t = time.perf_counter()
        navigate(h.name, start_url)
        url = get_url(h.name)
        if "Python_(programming_language)" not in url:
            print(f"GATE FAILED: the session is on {url!r}, not the article")
            return 1
        html = content(h.name)
        print(f"navigate + content: {time.perf_counter() - t:.2f}s, {len(html):,} characters")
        try:
            from speedrun.links import extract_candidates  # Lane B
            from speedrun.wiki import canonical_title_from_html
        except ImportError:
            print("Lane B's links.py / wiki.py aren't in this checkout yet; skipping the hop")
            return 0
        before = canonical_title_from_html(html)
        cands = extract_candidates(html)
        move = next(c for c in cands if not c.is_redirect and c.title != before)
        t = time.perf_counter()
        navigate(h.name, move.href)
        after = canonical_title_from_html(content(h.name))
        print(f"{len(cands)} legal moves on {before!r}; hop via {move.text!r} landed on "
              f"{after!r} in {time.perf_counter() - t:.2f}s")
        return 0 if after != before else 1
    finally:
        stop_session(h.name, session_id=h.id)
        stop_session(h.name, session_id=h.id)
        left = [s for s in list_sessions() if s.get("name") == h.name]
        print(f"stopped twice (idempotent); still running: {left or 'nothing'}")


if __name__ == "__main__":
    sys.exit(_smoke())
