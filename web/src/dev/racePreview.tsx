/**
 * Lane A + Lane B integration harness. Lane B, dev-only.
 *
 *     npm --prefix web run dev  ->  http://localhost:5173/race-preview.html
 *
 * Drives Lane A's REAL store through its public API and renders Lane B's REAL
 * Race screen, so the seam between them is exercised before App.tsx is wired.
 * Touches nothing Lane A owns. Delete once App.tsx imports Race directly —
 * which is a one-line change in their file, replacing <RaceStandIn /> with
 * <Race />.
 *
 * Uses the network (startRace fetches the start article) and the MOCK agent
 * feed, since `?agent=real` is unset. Add ?agent=real once Lane C's server is up.
 */
import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import Race from "../screens/Race";
import { Abandoned } from "../screens/Abandoned";
import { Results } from "../screens/Results";
import { PAIRS } from "../lib/pairs";
import { playerNavigated, startRace, useGame } from "../state/gameStore";
import { hopsFor } from "../agent/mockFeed";
import type { Difficulty } from "../agent/types";
import "../styles/theme.css";

function Harness() {
  const game = useGame();
  const [err, setErr] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const begin = (difficulty: Difficulty) => {
    const pool = PAIRS[difficulty];
    const pair = pool[Math.floor(Math.random() * pool.length)];
    setStarted(true);
    setErr(null);
    startRace({ start: pair.start, target: pair.target, difficulty }).catch((e) =>
      setErr(e instanceof Error ? e.message : String(e)),
    );
  };

  useEffect(() => {
    document.title = `Race preview — ${game.phase}`;
  }, [game.phase]);

  if (!started) {
    return (
      <main className="grid min-h-screen place-items-center p-8 font-body">
        <div className="on-dark w-[min(560px,92vw)] rounded-hero bg-card-green p-10 shadow-hero">
          <h1 className="font-display text-4xl leading-tight text-text-on-dark">
            race screen preview
          </h1>
          <p className="mt-4 text-text-on-dark-muted">
            Drives Lane A&rsquo;s store and Lane B&rsquo;s Race screen against a
            real article and the mock agent feed. Pick a difficulty.
          </p>
          <div className="mt-8 flex gap-3">
            {(["easy", "medium", "hard"] as Difficulty[]).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => begin(d)}
                className="rounded-pill bg-accent-black px-6 py-3 font-medium text-text-on-dark"
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      </main>
    );
  }

  if (err) {
    return (
      <main className="grid min-h-screen place-items-center p-8 font-body">
        <p className="max-w-lg text-error">{err}</p>
      </main>
    );
  }

  // Route exactly as App.tsx does, or the Results screen is never exercised —
  // which is how an earlier version of this harness left CP2's "Setup -> Race
  // -> Results end to end" looking like someone else's problem. Setup is still
  // skipped on purpose: this harness starts a race directly.
  return (
    <>
      {game.phase === "abandoned" ? (
        <Abandoned />
      ) : game.phase === "finished" ? (
        <Results />
      ) : (
        <Race />
      )}
      <DevBar />
    </>
  );
}

/**
 * DEV ONLY. Forces a human win so the win path can actually be exercised.
 *
 * It exists because the mock agent finishes in ~6 seconds and `makeFeed` (Lane
 * A's) ignores mockFeed's speed multiplier, so there is no way to slow the agent
 * down from here without editing their file. Clicking a real chain of links to
 * the target inside that window is not practical, and "win detection both
 * directions" is a CP2 requirement that had only ever been exercised in the
 * agent direction.
 *
 * This calls the SAME store action `ArticleFrame` calls — `playerNavigated` —
 * so it drives the real referee, the real win check and the real freeze. It is
 * not a mock of the win; it is the win, with the clicking skipped.
 */
function DevBar() {
  const game = useGame();
  const armed = game.phase === "racing";

  const [armedAt, setArmedAt] = useState<number | null>(null);

  const win = useCallback(() => {
    playerNavigated({
      title: game.targetTitle,
      anchorText: `${game.targetTitle} (simulated click)`,
    });
  }, [game.targetTitle]);

  /**
   * R5, the photo finish. The spec wants the mock to land ~400 ms AFTER a
   * player win, which is a one-second window nobody can hit by hand — so
   * compute it instead of reflex-testing it.
   *
   * mockFeed's schedule is deterministic: per hop it emits `thinking` at +700,
   * `pick` at +350, `arrive` at +1400, and carries `at` forward. So the agent
   * reaches the target at exactly hops x 2450 ms after GO. Win 400 ms before
   * that and the two landings are 400 ms apart by construction.
   */
  const MOCK_HOP_MS = 2450;
  const photoFinish = useCallback(() => {
    if (!armed || game.t0 == null || !game.pair) return;
    const agentWinAt = hopsFor(game.pair).length * MOCK_HOP_MS;
    const fireAt = game.t0 + agentWinAt - 400;
    const wait = Math.max(0, fireAt - performance.now());
    setArmedAt(Math.round(wait));
    window.setTimeout(win, wait);
  }, [armed, game.t0, game.pair, win]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "w" && armed) win();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [win, armed]);

  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2">
      <div className="flex items-center gap-3 rounded-pill bg-accent-black/90 px-4 py-2 text-sm text-text-on-dark shadow-hero backdrop-blur">
        <span className="text-text-on-dark-muted">dev · {game.phase}</span>
        <button
          type="button"
          onClick={win}
          disabled={!armed}
          className="rounded-pill bg-text-on-dark px-4 py-1.5 font-medium text-accent-black disabled:opacity-40"
        >
          ⚡ Win as player (W)
        </button>
        <button
          type="button"
          onClick={photoFinish}
          disabled={!armed || armedAt != null}
          className="rounded-pill border border-text-on-dark/40 px-4 py-1.5 font-medium text-text-on-dark disabled:opacity-40"
          title="Schedules your win 400ms before the mock agent lands"
        >
          📸 Photo finish (R5)
        </button>
        {armedAt != null && game.phase !== "finished" && (
          <span className="text-text-on-dark-muted">firing in {armedAt}ms…</span>
        )}
        {game.phase === "finished" && (
          <span className="text-text-on-dark-muted">
            winner: <strong className="text-text-on-dark">{game.winner}</strong>
            {game.reason ? ` · ${game.reason}` : ""}
            {game.marginMs != null ? ` · margin ${Math.round(game.marginMs)}ms` : ""}
          </span>
        )}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
