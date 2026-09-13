"""The agent's race loop, and where its pages come from. Lane C. PLAN.md §4.E, as amended
by FRONTEND.md §7.

One race: arm (check both titles, park the browser on the start article, emit `ready`), wait
for the gun, then hop until the page's CANONICAL title matches the target or something else
ends it. Every ending except a client stop emits exactly one `done`, and the browser is
ALWAYS released, because a leaked Steel session is the one unacceptable outcome
(FRONTEND.md §2.7).

FRONTEND.md §7's six changes to PLAN.md §4.E: it takes canonical titles (they're checked
again here, because the CLI passes typed ones); it emits FRONTEND.md §6.1 events; it waits on
a go flag; it checks a stop flag between steps; it can race on a browser someone else
started; and NoCandidatesError is still a dead end. FRONTEND.md §0 cut banned_titles, the
stuck-retry and the 700 ms second look.

The page sources live here too: `SteelSource` (the real browser the audience watches) and
`HttpSource` (FRONTEND.md §9.3 lever 2, `--page-source http`, with the same loop, extractor
and LLM). So does `canonicalize()`, the MediaWiki check that race endpoints exist. They're
in this file because Lane C owns exactly the files in .agents/skills/lane-c-agent/SKILL.md.
"""

from __future__ import annotations

import dataclasses
import json
import os
import ssl
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Mapping
from urllib.parse import urljoin

from speedrun import events as ev
from speedrun import steel_client
from speedrun.types import Candidate, PickResult, RaceResult, SessionHandle

WIKI_ORIGIN = "https://en.wikipedia.org/"
API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "WikiRacer/1.0 (hackathon project; https://github.com/kieran-ym/WikiRacer)"
HTTP_TIMEOUT_S = 20.0
DEFAULT_GO_TIMEOUT_S = 300.0
SYSTEM_CA_BUNDLES = ("/etc/ssl/cert.pem",                   # macOS
                     "/etc/ssl/certs/ca-certificates.crt",  # Debian / Ubuntu
                     "/etc/pki/tls/certs/ca-bundle.crt")    # Fedora / RHEL


# =========================================================================== Wikipedia over HTTPS


class WikiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status, self.url = status, url


def fallback_cafile(paths: ssl.DefaultVerifyPaths, *, candidates=SYSTEM_CA_BUNDLES,
                    exists: Callable[[str], bool] = os.path.exists,
                    env: Mapping[str, str] = os.environ) -> str | None:
    """A CA bundle to load when this Python has none of its own.

    python.org's macOS builds ship without one (`cafile=None, capath=None`, verified on the
    team machine), so every urllib HTTPS request fails with CERTIFICATE_VERIFY_FAILED.
    """
    if env.get(paths.openssl_cafile_env) or env.get(paths.openssl_capath_env):
        return None  # someone pointed OpenSSL somewhere on purpose
    if (paths.cafile and exists(paths.cafile)) or (paths.capath and exists(paths.capath)):
        return None
    return next((c for c in candidates if exists(c)), None)


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    extra = fallback_cafile(ssl.get_default_verify_paths())
    if extra:
        ctx.load_verify_locations(cafile=extra)
    return ctx


def http_get(url: str, timeout: float = HTTP_TIMEOUT_S) -> str:
    """GET a Wikipedia URL. Anything but a 200 raises WikiError. A 429 body must never reach
    a parser: that's how this project already lost two races (CLAUDE.md rule 8)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        hint = " (Wikipedia is rate-limiting us, so slow down)" if e.code == 429 else ""
        raise WikiError(f"Wikipedia answered HTTP {e.code} for {url}{hint}", status=e.code, url=url) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise WikiError(f"Couldn't reach Wikipedia for {url}: {getattr(e, 'reason', e)}", url=url) from None
    if status != 200:
        raise WikiError(f"Wikipedia answered HTTP {status} for {url}", status=status, url=url)
    return body.decode("utf-8", errors="replace")


def http_get_json(url: str, timeout: float = HTTP_TIMEOUT_S) -> dict:
    text = http_get(url, timeout=timeout)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise WikiError(f"Wikipedia sent something that isn't JSON (a captive portal?): {text[:120]!r}",
                        url=url) from None
    if not isinstance(data, dict):
        raise WikiError(f"Wikipedia sent JSON that isn't an object: {text[:120]!r}", url=url)
    if "error" in data:
        err = data["error"]
        raise WikiError(f"Wikipedia API error: {err.get('info') if isinstance(err, dict) else err}", url=url)
    return data


def canonicalize(titles: list[str], timeout: float = HTTP_TIMEOUT_S) -> dict[str, str | None]:
    """{typed: canonical article title, or None if no such article}, in one request.

    Resolves the way Wikipedia does: normalization ("barack obama" → "Barack obama"), then
    redirects ("Barack obama" → "Barack Obama"; "Snakes" → "Snake"). Missing pages and
    non-article namespaces (Talk:, File:, ...) come back None. This is the same
    `action=query&redirects=1` the frontend validates with, so both racers agree on the
    target by construction. The HTML can't be trusted with this, because a missing article's
    read view carries a canonical link that repeats the typo (docs/steel-json-shapes.md,
    trap 8). Look-ups are keyed by the exact string sent; keying them by a different
    spelling was FRONTEND.md §5.1 bug (a).
    """
    for t in titles:
        if "|" in t:
            raise ValueError(f"{t!r}: '|' separates titles in a MediaWiki query, and no title contains one")
    out: dict[str, str | None] = {t: None for t in titles}
    wanted = [t for t in dict.fromkeys(titles) if t.strip()]
    if not wanted:
        return out
    url = API_URL + "?" + urllib.parse.urlencode({
        "action": "query", "titles": "|".join(wanted), "redirects": 1,
        "format": "json", "formatversion": 2})
    q = http_get_json(url, timeout=timeout).get("query") or {}
    normalized = {n.get("from"): n.get("to") for n in q.get("normalized", [])}
    redirects = {r.get("from"): r.get("to") for r in q.get("redirects", [])}
    by_title = {p.get("title"): p for p in q.get("pages", [])}
    for typed in wanted:
        title = normalized.get(typed, typed)
        for _ in range(5):  # a redirect chain lists every link; stop on a cycle
            if title not in redirects:
                break
            title = redirects[title]
        page = by_title.get(title)
        if page and page.get("ns") == 0 and not page.get("missing") and not page.get("invalid"):
            out[typed] = page["title"]
    return out


# =========================================================================== page sources
# Both hand the race the READ VIEW HTML (absolute hrefs + <link rel="canonical">): the flavour
# Lane B's links.py / wiki.py are built and tested against. Never rest_v1 (CLAUDE.md rule 1).


class SteelSource:
    """The agent's real browser, in Steel's cloud. The audience watches `live_url`."""

    kind = "steel"

    def __init__(self, handle: SessionHandle | None = None, *, started_at: float | None = None,
                 session_timeout_ms: int = 900_000, name_prefix: str = "wikiracer",
                 clock: Callable[[], float] = time.monotonic, expiry_margin_s: float = 20.0):
        self.handle = handle
        self.clock = clock
        self.session_timeout_ms = session_timeout_ms
        self.name_prefix = name_prefix
        self.expiry_margin_s = expiry_margin_s
        self._started_at = started_at if started_at is not None else (clock() if handle else None)
        self._lock = threading.Lock()

    @property
    def session_id(self) -> str:
        return self.handle.id if self.handle else ""

    @property
    def live_url(self) -> str:
        return self.handle.live_url if self.handle else ""

    def open(self) -> None:
        if self.handle is None:
            self._started_at = self.clock()
            self.handle = steel_client.start_session(
                session_timeout_ms=self.session_timeout_ms, inactivity_timeout_ms=0,
                name_prefix=self.name_prefix)

    def goto(self, url: str) -> tuple[str, float]:
        """Navigate, then read the page. Returns (html, when navigation finished): the
        moment the agent arrived, not the moment we got round to reading the HTML."""
        self._guard()
        steel_client.navigate(self.handle.name, url)
        loaded_at = self.clock()
        return steel_client.content(self.handle.name), loaded_at

    def _guard(self) -> None:
        if self.handle is None or self._started_at is None:
            raise steel_client.SteelSessionLost("SteelSource.goto() before open()")
        lifetime_s = self.handle.session_timeout_ms / 1000
        if self.clock() - self._started_at > lifetime_s - self.expiry_margin_s:
            raise steel_client.SteelSessionLost(
                f"Steel session {self.handle.name} is within {self.expiry_margin_s:g}s of its "
                f"{lifetime_s:g}s lifetime. Refusing to send it commands, because Steel would "
                "silently start a fresh session on about:blank (docs/steel-json-shapes.md, trap 1).")

    def close(self) -> None:
        """Stop the session, re-sending the idempotent stop BY NAME every time, so a session
        that a stray command re-created under our name is torn down too. Never raises: this
        runs in `finally` blocks, and a failed stop must not mask the error that got us here."""
        if self.handle is None:
            return
        with self._lock:
            try:
                steel_client.stop_session(self.handle.name, session_id=self.handle.id)
            except steel_client.SteelError as e:
                print(f"[steel] WARNING: could not stop {self.handle.name} ({self.handle.id}): {e}. "
                      "Check `steel browser sessions`.", file=sys.stderr)


class HttpSource:
    """No browser: the read view over HTTPS. No live view, so `live_url` is ""."""

    kind = "http"
    session_id = "http"
    live_url = ""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic, timeout: float = HTTP_TIMEOUT_S):
        self.clock, self.timeout = clock, timeout

    def open(self) -> None:
        pass

    def goto(self, url: str) -> tuple[str, float]:
        if not url.startswith(WIKI_ORIGIN):
            raise WikiError(f"refusing to fetch a URL that isn't on en.wikipedia.org: {url!r}", url=url)
        html = http_get(url, timeout=self.timeout)
        return html, self.clock()

    def close(self) -> None:
        pass


# =========================================================================== the rules and the picker


@dataclass(frozen=True)
class GameRules:
    """The game rule and the title primitives. Lane B owns the real ones (speedrun/links.py,
    speedrun/wiki.py). The loop depends only on this shape, so it can be tested on its own."""

    extract_candidates: Callable[[str], list[Candidate]]
    find_target: Callable[[list[Candidate], str], Candidate | None]
    canonical_title: Callable[[str], str]
    titles_match: Callable[[str, str], bool]
    url_from_title: Callable[[str], str]
    title_from_url: Callable[[str], str]


def lane_b_rules() -> GameRules:
    from speedrun import links, wiki  # Lane B. Imported late so this module loads without them.

    return GameRules(
        extract_candidates=links.extract_candidates,
        find_target=links.find_target,
        canonical_title=wiki.canonical_title_from_html,
        titles_match=wiki.titles_match,
        url_from_title=wiki.url_from_title,
        title_from_url=wiki.title_from_url,
    )


@dataclass(frozen=True)
class PickerFns:
    """`choose` has PLAN.md §2.2's choose_link signature; `no_candidates` is what it raises
    for an empty list (a dead end, not an error)."""

    choose: Callable[..., PickResult]
    no_candidates: type[BaseException]


def llm_picker() -> PickerFns:
    try:
        from speedrun import picker  # Lane B
    except ImportError as e:
        raise RuntimeError(
            "speedrun/picker.py (Lane B) isn't in this checkout yet. Merge it, or run with "
            "`--picker first` to exercise the loop without an LLM.") from e
    return PickerFns(choose=picker.choose_link, no_candidates=picker.NoCandidatesError)


class _NeverRaised(Exception):
    pass


def first_link_picker() -> PickerFns:
    """DEV ONLY, no LLM. Picks the first candidate it's shown (already visited-filtered), so
    Steel, the loop and the event stream can be exercised without an API key. Never the
    default: first links famously lead to Philosophy, not to your target."""

    def choose(client, model, current_title, target_title, visited, candidates, hop, max_hops,
               banned_titles=None):
        return PickResult(candidate=candidates[0], reason="[dev picker] first unvisited link",
                          was_fallback=True)

    return PickerFns(choose=choose, no_candidates=_NeverRaised)


_ANTHROPIC_HINTS = {
    "AuthenticationError": "Anthropic rejected the API key (check ANTHROPIC_API_KEY in .env)",
    "PermissionDeniedError": "This Anthropic key isn't allowed to do that",
    "NotFoundError": "Anthropic doesn't know that model (check the model name)",
    "BadRequestError": "Anthropic rejected the request",
    "RateLimitError": "Anthropic is rate-limiting us",
    "APITimeoutError": "Anthropic took too long to answer",
    "APIConnectionError": "Couldn't reach Anthropic",
}


def describe(exc: BaseException) -> str:
    """One host-readable line. Never a stack trace on a projector."""
    text = getattr(exc, "message", None) or str(exc) or type(exc).__name__
    if type(exc).__module__.split(".")[0] == "anthropic":
        hint = _ANTHROPIC_HINTS.get(type(exc).__name__)
        if hint:
            return f"{hint}: {text}"
    return text


class ArmingError(RuntimeError):
    """The race can't start. The message is for the host."""


class _Stopped(Exception):
    """The client stopped the race (POST /stop, Ctrl+C). Not an error."""


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (steel_client.SteelSessionLost, steel_client.SteelNotInstalled)):
        return False
    if isinstance(exc, steel_client.SteelError):  # includes SteelTimeout
        return True
    if isinstance(exc, WikiError):
        return exc.status is None or exc.status == 429 or exc.status >= 500
    return False


# =========================================================================== the race


class AgentRace:
    """One agent race. Build it, then call `run()` (which blocks) from the thread that owns
    the browser: only that thread ever sends the browser commands or stops it."""

    def __init__(self, start: str, target: str, *, model: str, max_hops: int, use_find_target: bool,
                 source: Any, log: ev.EventLog, rules: GameRules, picker: PickerFns,
                 resolve_titles: Callable[[list[str]], dict[str, str | None]] = canonicalize,
                 client: Any = None, stop: threading.Event | None = None,
                 go: threading.Event | None = None, go_timeout_s: float = DEFAULT_GO_TIMEOUT_S):
        self.start_input, self.target_input = start, target
        self.model, self.max_hops, self.use_find_target = model, max_hops, use_find_target
        self.source, self.log, self.rules = source, log, rules
        self.picker, self.resolve_titles, self.client = picker, resolve_titles, client
        self.stop = stop or threading.Event()
        self.go = go  # None: no gate, the gun fires as soon as the agent is ready (cli.py)
        self.go_timeout_s = go_timeout_s
        self.start_title: str | None = None
        self.target_title: str | None = None
        self.path: list[str] = []
        self.hops = 0
        self.result: RaceResult | None = None
        self._html: str | None = None

    # ------------------------------------------------------------------ lifecycle

    def run(self) -> RaceResult:
        """Arm, wait for the gun, race. Always releases the browser."""
        try:
            self._arm()
            self._wait_for_gun()
            result = self._race()
        except _Stopped:
            result = self._result(reason="error", error="stopped")
        except Exception as exc:  # noqa: BLE001 - anything else ends the agent's race, loudly
            result = self._result(reason="error", error="stopped") if self.stop.is_set() else self._fail(exc)
        finally:
            self.source.close()
        self.result = result
        return result

    def _fail(self, exc: BaseException) -> RaceResult:
        if isinstance(exc, ArmingError):
            message = str(exc)
        else:
            message = describe(exc)
            traceback.print_exception(exc, file=sys.stderr)  # for the terminal, not the projector
        self.log.emit(ev.error(message=message, fatal=True))
        self.log.emit(ev.done(reason="error", hops=self.hops, message=message))
        return self._result(reason="error", error=message)

    def _end(self, reason: str, message: str | None = None) -> RaceResult:
        self.log.emit(ev.done(reason=reason, hops=self.hops, message=message))
        return self._result(reason=reason)

    def _result(self, *, reason: str, error: str | None = None) -> RaceResult:
        won = reason == "won"
        return RaceResult(won=won, winner="bot" if won else "none",
                          elapsed_s=round(self.log.elapsed_s(), 3), hops=self.hops,
                          path=list(self.path), reason=reason, error=error)

    def _check_stop(self) -> None:
        if self.stop.is_set():
            raise _Stopped()

    # ------------------------------------------------------------------ arming

    def _arm(self) -> None:
        start_typed = self.rules.title_from_url(self.start_input)
        target_typed = self.rules.title_from_url(self.target_input)
        resolved = self.resolve_titles([start_typed, target_typed])
        start, target = resolved.get(start_typed), resolved.get(target_typed)
        for typed, found in ((start_typed, start), (target_typed, target)):
            if not found:
                raise ArmingError(f"There is no Wikipedia article called {typed!r}.")
        if self.rules.titles_match(start, target):
            raise ArmingError(f"Start and target are the same article ({start}).")
        self.target_title = target
        self._check_stop()
        self.source.open()
        self._check_stop()
        html, _ = self._goto(self.rules.url_from_title(start), what=f"the start article {start!r}")
        landed = self.rules.canonical_title(html)
        if not self.rules.titles_match(landed, start):
            self.log.emit(ev.error(message=f"Wikipedia resolved the start to {landed!r}, not "
                                           f"{start!r}; racing from {landed!r}.", fatal=False))
        self.start_title, self._html, self.path = landed, html, [landed]
        self._check_stop()
        self.log.emit(ev.ready(session_id=self.source.session_id, live_url=self.source.live_url))

    def _wait_for_gun(self) -> None:
        if self.go is None:
            self.log.mark_go()
            return
        deadline = time.monotonic() + self.go_timeout_s
        while not self.go.wait(0.05):
            self._check_stop()
            if time.monotonic() > deadline:
                raise ArmingError(f"The agent was ready but the race never started ({self.go_timeout_s:g}s "
                                  "without a GO), so its browser was released.")
        self._check_stop()
        self.log.mark_go()  # a no-op when POST /go already fired it (the first gun wins)

    # ------------------------------------------------------------------ racing

    def _race(self) -> RaceResult:
        current, target, html = self.start_title, self.target_title, self._html
        visited = [current]
        for hop in range(1, self.max_hops + 1):
            self._check_stop()
            cands = [c for c in self.rules.extract_candidates(html)
                     if not self.rules.titles_match(c.title, current)]
            self.log.emit(ev.thinking(article=current, n_candidates=len(cands)))
            choice, reason, was_fallback = self._choose(current, target, visited, cands, hop)
            if choice is None:
                return self._end("dead_end", message=reason)
            self._check_stop()
            self.log.emit(ev.pick(from_=current, to=choice.title, anchor_text=choice.text or choice.title,
                                  reason=reason or "", was_fallback=was_fallback))
            html, loaded_at = self._goto(urljoin(WIKI_ORIGIN, choice.href), what=repr(choice.title))
            self._check_stop()
            landed = self.rules.canonical_title(html)  # THE win check reads this. Never the URL.
            self.hops = hop
            self.path.append(landed)
            visited.append(landed)
            self.log.emit(ev.arrive(article=landed, hop=hop), at_s=loaded_at)
            if self.rules.titles_match(landed, target):
                return self._end("won")
            current = landed
        return self._end("hop_limit_reached")

    def _choose(self, current: str, target: str, visited: list[str], cands: list[Candidate],
                hop: int) -> tuple[Candidate | None, str, bool]:
        if not cands:
            return None, f"{current} has no links left to follow.", False
        if self.use_find_target:
            # PLAN.md §4.A: a visible target is a guaranteed win. No LLM call, so no chance
            # of an LLM error at the winning move. Easy tier turns this off (FRONTEND.md §5.5).
            hit = self.rules.find_target(cands, target)
            if hit is not None:
                return hit, f"{target} is linked right here.", False
        # Structural loop prevention (PLAN.md §4.C): drop what we've stood on, unless that
        # would leave nothing. Then renumber from 0, because the picker renders Candidate.index
        # verbatim, and this numbering is the plan's only silent-wrong-answer bug.
        seen = {v.casefold() for v in visited}
        pool = [c for c in cands if c.title.casefold() not in seen] or cands
        pool = [dataclasses.replace(c, index=i) for i, c in enumerate(pool)]
        try:
            picked = self.picker.choose(self.client, self.model, current, target, list(visited),
                                        pool, hop, self.max_hops, None)
        except self.picker.no_candidates:
            return None, f"{current} has no links left to follow.", False
        if picked is None or picked.candidate is None:
            reason = (picked.reason if picked else "") or "The picker found nothing to click."
            return None, reason, bool(picked and picked.was_fallback)
        return picked.candidate, picked.reason, picked.was_fallback

    def _goto(self, url: str, what: str) -> tuple[str, float]:
        """One retry for a transient failure (Steel hiccup, Wikipedia 429/5xx). Then it's fatal."""
        for attempt in (1, 2):
            try:
                return self.source.goto(url)
            except Exception as exc:  # noqa: BLE001
                if self.stop.is_set():
                    raise _Stopped() from exc
                if attempt == 2 or not _is_transient(exc):
                    raise
                self.log.emit(ev.error(message=f"Loading {what} failed ({describe(exc)}); retrying once.",
                                       fatal=False))
        raise AssertionError("unreachable")


def run_race(start: str, target: str, model: str, max_hops: int = 25, *, use_find_target: bool = True,
             source: Any = None, log: ev.EventLog | None = None, picker: PickerFns | None = None,
             client: Any = None, stop: threading.Event | None = None,
             go: threading.Event | None = None) -> RaceResult:
    """PLAN.md §2.2's entry point: `start`/`target` exactly as typed (title or URL). Builds
    the real pieces (Steel, Lane B's rules, the LLM picker) for anything not handed in."""
    race = AgentRace(start, target, model=model, max_hops=max_hops, use_find_target=use_find_target,
                     source=source or SteelSource(name_prefix="wikiracer-cli"),
                     log=log or ev.EventLog(), rules=lane_b_rules(), picker=picker or llm_picker(),
                     resolve_titles=canonicalize, client=client, stop=stop, go=go)
    return race.run()
