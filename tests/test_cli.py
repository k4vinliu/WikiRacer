"""speedrun/cli.py: the headless agent-only race, Lane C's regression harness and the
"the browser died, we still have a demo" insurance (FRONTEND.md §8)."""

from __future__ import annotations

import inspect
import io
import signal
import threading
import time

import pytest
from fakes import FakeSource, FakeWiki, NoCandidates, scripted

from speedrun import cli, config, race
from speedrun import events as ev
from speedrun.types import PickResult, RaceResult


def args(*extra: str):
    return cli.parse_args(["--start", "Snakes", "--target", "WWII", *extra])


def agent_for(wiki, start, target, picker, source, max_hops=25):
    return race.AgentRace(start, target, model="claude-haiku-4-5", max_hops=max_hops, use_find_target=True,
                          source=source, log=ev.EventLog(), rules=wiki.rules(),
                          resolve_titles=wiki.resolve_titles, picker=picker)


def test_defaults():
    a = args()
    assert (a.difficulty, a.max_hops, a.page_source, a.picker, a.model) == ("medium", 25, "steel", "llm", None)


def test_start_and_target_are_required():
    with pytest.raises(SystemExit):
        cli.parse_args(["--start", "Cat"])


@pytest.mark.parametrize("extra, expected", [
    ((), ("claude-haiku-4-5", True)),
    (("--difficulty", "easy"), ("claude-haiku-4-5", False)),
    (("--difficulty", "hard"), ("claude-sonnet-5", True)),
    (("--no-find-target",), ("claude-haiku-4-5", False)),
    (("--model", "claude-sonnet-5"), ("claude-sonnet-5", True)),
])
def test_the_tier_sets_the_model_and_find_target(extra, expected):
    assert cli.settings(args(*extra), env={}) == expected


def test_summaries_say_how_it_ended():
    won = RaceResult(won=True, winner="bot", elapsed_s=12.34, hops=2,
                     path=["Snake", "Reptile", "World War II"], reason="won")
    line = cli.summarize(won)
    assert "WON" in line and "Snake -> Reptile -> World War II" in line and "12.3" in line
    gave_up = RaceResult(won=False, winner="none", elapsed_s=40.0, hops=25, path=["A"], reason="hop_limit_reached")
    assert "hop limit" in cli.summarize(gave_up)
    error = RaceResult(won=False, winner="none", elapsed_s=0.0, hops=0, path=[], reason="error",
                       error="There is no Wikipedia article called 'Xyzzy'.")
    assert "Xyzzy" in cli.summarize(error)


def test_run_headless_runs_the_race_to_the_end_and_releases_the_browser():
    wiki = FakeWiki({"Cat": ["Ancient Egypt"], "Ancient Egypt": ["Napoleon"], "Napoleon": []})
    picker, _ = scripted("Ancient Egypt")
    src = FakeSource(wiki)
    result, interrupted = cli.run_headless(agent_for(wiki, "Cat", "Napoleon", picker, src))
    assert (result.won, interrupted, src.closed) == (True, False, True)


def test_ctrl_c_stops_the_race_and_still_releases_the_browser():
    class SlowSource(FakeSource):
        def goto(self, url):
            time.sleep(0.05)
            return super().goto(url)

    def choose(client, model, current_title, target_title, visited, candidates, hop, max_hops, banned_titles=None):
        return PickResult(candidate=candidates[0], reason="going round in circles", was_fallback=False)

    wiki = FakeWiki({"A": ["B"], "B": ["A"], "T": []})
    src = SlowSource(wiki)
    agent = agent_for(wiki, "A", "T", race.PickerFns(choose, NoCandidates), src, max_hops=10_000)
    threading.Timer(0.3, signal.raise_signal, args=(signal.SIGINT,)).start()
    err = io.StringIO()
    result, interrupted = cli.run_headless(agent, err=err)
    assert interrupted and src.closed
    assert "stopping Steel session" in err.getvalue()


def test_a_missing_key_is_one_readable_line_and_exit_2(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config, "load_env", lambda *a, **k: None)
    monkeypatch.setattr(config, "preflight_steel", lambda: pytest.fail("checked Steel before the key"))
    assert cli.main(["--start", "Cat", "--target", "Napoleon"]) == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err and "Traceback" not in err


def test_the_host_presses_enter_finish_is_gone():
    # FRONTEND.md §8: the referee is gameStore.ts now. The CLI must not grow back a thread that
    # reads the keyboard to call the human's finish.
    source = inspect.getsource(cli)
    assert "readline" not in source and "input(" not in source
