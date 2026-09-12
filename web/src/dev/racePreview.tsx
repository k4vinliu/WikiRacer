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
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import Race from "../screens/Race";
import { PAIRS } from "../lib/pairs";
import { startRace, useGame } from "../state/gameStore";
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

  // arming / countdown / racing / finished all render through the real screen;
  // the header shows which phase we are in.
  return <Race />;
}

createRoot(document.getElementById("root")!).render(<Harness />);
