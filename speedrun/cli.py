"""The headless agent-only race. Lane C. PLAN.md §4.E, as amended by FRONTEND.md §8.

Lane C's regression harness, and the "the browser died, we still have a demo" insurance: the
same loop the server runs, printed to the terminal, one line per event. There's no gate and no
human in it. The referee is gameStore.ts now (FRONTEND.md §7), so PLAN.md's
host-presses-Enter finish is gone on purpose.

    python3.11 -m speedrun.cli --start "Snakes" --target "WWII"
    python3.11 -m speedrun.cli --start Cat --target Napoleon --picker first --page-source http

FRONTEND.md §10 demotes PLAN.md §4.E's acceptance runs to this headless regression suite:

    --start "Python (programming language)" --target "Guido van Rossum"  # one hop, via find_target
    --start "Cat" --target "Nuclear weapon"
    --start "Snakes" --target "WWII"   # both endpoints are redirects: the run v1 would have lost

and afterwards `steel browser sessions` must list nothing.
"""

from __future__ import annotations

import argparse
import sys
import threading
from typing import TextIO

from speedrun import config, console, race
from speedrun import events as ev
from speedrun.types import RaceResult

SESSION_PREFIX = "wikiracer-cli"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python3.11 -m speedrun.cli",
                                 description="Race the agent on its own, headless (Lane C's regression harness).")
    ap.add_argument("--start", required=True, help="start article: a title or a URL, exactly as typed")
    ap.add_argument("--target", required=True, help="target article: a title or a URL, exactly as typed")
    ap.add_argument("--difficulty", choices=("easy", "medium", "hard"), default="medium",
                    help="the agent settings from FRONTEND.md §5.5 (default: medium)")
    ap.add_argument("--model", help="override the tier's model")
    ap.add_argument("--max-hops", type=int, default=config.DEFAULT_MAX_HOPS)
    ap.add_argument("--no-find-target", action="store_true",
                    help="don't take a visible target without asking the LLM (easy does this)")
    ap.add_argument("--page-source", choices=("steel", "http"), default="steel",
                    help="http = no browser, same loop (FRONTEND.md §9.3 lever 2)")
    ap.add_argument("--picker", choices=("llm", "first"), default="llm",
                    help="first = DEV ONLY: always the first unvisited link, no API key needed")
    return ap.parse_args(argv)


def settings(args: argparse.Namespace, env=None) -> tuple[str, bool]:
    """(model, use_find_target) for these arguments: the tier's, unless a flag overrides it."""
    tier = config.tiers(env)[args.difficulty]
    return args.model or tier.model, tier.use_find_target and not args.no_find_target


def summarize(result: RaceResult) -> str:
    path = " -> ".join(result.path or []) or "(never left the start)"
    if result.won:
        return f"AGENT WON in {result.hops} hop(s), {result.elapsed_s:.1f}s: {path}"
    if result.error == "stopped":
        return f"Stopped after {result.hops} hop(s)."
    if result.reason == "error":
        return f"RACE ENDED EARLY: {result.error}"
    how = {"hop_limit_reached": "gave up at the hop limit",
           "dead_end": "hit a dead end"}.get(result.reason or "", result.reason or "stopped")
    return f"The agent {how} after {result.hops} hop(s), {result.elapsed_s:.1f}s: {path}"


def run_headless(agent: race.AgentRace, err: TextIO | None = None) -> tuple[RaceResult | None, bool]:
    """Run the race on its own thread so that Ctrl+C stops it cleanly: the thread that owns the
    browser notices the stop flag and releases the session itself. Returns (result, interrupted).

    We wait on an Event, NOT on `thread.join()`, and that is load-bearing. A KeyboardInterrupt
    delivered while the main thread is blocked inside `Thread.join(timeout)` lands in CPython's
    bpo-45274 mitigation, which cannot tell "we acquired the lock then got interrupted" from
    "we were still waiting for it": it sees the child's `_tstate_lock` held, releases it, and
    calls `Thread._stop()`. The Thread object is now permanently marked dead even though the
    thread is still running, so `is_alive()` returns False and EVERY later `join()` returns in
    0.000s. Measured on CPython 3.11.15 with no project code involved.

    That is precisely the Ctrl+C path, so the old `thread.join(60)` here returned instantly,
    `main()` returned 130, and the interpreter tore down a daemon thread that had not reached
    `AgentRace.run()`'s `finally` yet -- leaking the Steel cloud session the README promises to
    release, and busting `steel browser sessions` must list nothing. An Event is not poisoned by
    the interrupt, and the race thread sets it AFTER `run()` returns, hence after `source.close()`.
    """
    err = err or sys.stderr
    box: dict[str, RaceResult] = {}
    finished = threading.Event()

    def target() -> None:
        try:
            box.update(result=agent.run())
        finally:
            # `run()` releases the browser in its own `finally`, so by the time this fires the
            # session is already stopped. Do not move this above the call.
            finished.set()

    thread = threading.Thread(target=target, name="agent-race", daemon=True)
    thread.start()
    try:
        while not finished.wait(0.2):
            pass
    except KeyboardInterrupt:
        print("\nstopping Steel session...", file=err, flush=True)
        agent.stop.set()
        try:
            if not finished.wait(60):
                print("the agent thread is still shutting down; run `steel browser sessions` and "
                      "`steel browser stop <name>` if one is left over.", file=err, flush=True)
        except KeyboardInterrupt:
            # A second Ctrl+C is the host saying "I don't care, let me out". Honour it, but say
            # plainly that we no longer know whether the browser was released.
            print("interrupted again; the Steel session may still be open. Check "
                  "`steel browser sessions`.", file=err, flush=True)
        return box.get("result"), True
    return box.get("result"), False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    model, use_find_target = settings(args)
    client = None
    try:
        if args.picker == "llm":
            client = config.make_client()
            config.preflight_anthropic(client, [model])
            picker = race.llm_picker()
        else:
            picker = race.first_link_picker()
        if args.page_source == "steel":
            ok, detail = config.preflight_steel()
            if not ok:
                raise config.ConfigError(detail)
            source = race.SteelSource(session_timeout_ms=config.DEFAULT_SESSION_TIMEOUT_MS,
                                      name_prefix=SESSION_PREFIX)
        else:
            source = race.HttpSource()
        rules = race.lane_b_rules()
    except (RuntimeError, ImportError) as e:  # ConfigError is a RuntimeError, and so is "picker.py isn't merged"
        print(f"error: {e}", file=sys.stderr)
        return 2
    log = ev.EventLog()
    log.add_listener(console.print_event)
    agent = race.AgentRace(args.start, args.target, model=model, max_hops=args.max_hops,
                           use_find_target=use_find_target, source=source, log=log, rules=rules,
                           picker=picker, client=client)
    print(f"racing {args.start!r} -> {args.target!r} | {args.difficulty}: {model}, find_target "
          f"{'on' if use_find_target else 'off'} | pages from {args.page_source} | picker {args.picker}",
          file=sys.stderr)
    result, interrupted = run_headless(agent)
    if interrupted:
        return 130
    print(summarize(result) if result else "The race thread did not finish.")
    return 0 if result and result.won else 1


if __name__ == "__main__":
    sys.exit(main())
