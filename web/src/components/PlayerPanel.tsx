/**
 * The human's half of the race. Lane B. FRONTEND.md §4.3.
 *
 * Owns the one piece of state Lane A's store deliberately does not: WHICH
 * article is currently loaded. `playerNavigated` records the move and
 * adjudicates the win; fetching the next page is a rendering concern, so it
 * lives here.
 *
 * Sequence on a click, and the order matters:
 *   1. tell the referee immediately — the player's timestamp is stamped at
 *      CLICK, not at fetch-resolve (FRONTEND.md §2.6 rule 2). A parse fetch is
 *      0.5-1.0s locally and 2-4s on bad wifi; stamping late would make the
 *      human's clock ~6x the tie window slower than the agent's.
 *   2. then fetch and swap the HTML.
 * If the race ends on step 1 the swap still completes harmlessly; the panel is
 * frozen by `interactive=false` either way.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import ArticleFrame, { type ArticleMove } from "./ArticleFrame";
import PathTrail from "./PathTrail";
import { describeLoadError, loadArticle } from "../lib/articleHtml";
import { markStartPainted, playerNavigated, useGame } from "../state/gameStore";

export function PlayerPanel() {
  const game = useGame();
  const [html, setHtml] = useState<string | null>(null);
  const [title, setTitle] = useState<string>(game.startTitle);
  const [stats, setStats] = useState({ n: 0, targetHere: false });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Guards an out-of-order fetch: a fast second click must not be overwritten
  // by the first click's slower response.
  const seq = useRef(0);

  // The start article arrives pre-fetched from the store, so the arming phase
  // has already paid for it and hop 1 paints instantly.
  useEffect(() => {
    if (game.startArticle && html === null) {
      setHtml(game.startArticle.html);
      setTitle(game.startArticle.title);
      markStartPainted();
    }
  }, [game.startArticle, html]);

  const go = useCallback(
    async (next: string) => {
      const mine = ++seq.current;
      setLoading(true);
      setError(null);
      try {
        const a = await loadArticle(next, game.targetTitle);
        if (mine !== seq.current) return; // a later click already won
        setHtml(a.html);
        setTitle(a.title);
      } catch (err) {
        if (mine !== seq.current) return;
        setError(describeLoadError(err));
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    },
    [game.targetTitle],
  );

  const onMove = useCallback(
    (move: ArticleMove) => {
      playerNavigated(move); // 1. referee first, always
      void go(move.title); // 2. then the page
    },
    [go],
  );

  const racing = game.phase === "racing";

  return (
    <section className="on-dark flex min-h-0 w-full flex-col rounded-card bg-card-green p-4 shadow-card">
      <header className="flex items-baseline justify-between gap-3 px-1 pb-3">
        <h2 className="min-w-0 truncate font-medium text-text-on-dark">
          <span className="text-text-on-dark-muted">you · </span>
          {title}
        </h2>
        <span className="flex shrink-0 items-baseline gap-2 text-sm">
          {/* The target indicator lives HERE, not in the header, because it is a
              fact about the page the player is looking at. The agent gets the
              same information free via links.find_target, so showing it
              restores symmetry rather than granting an advantage. */}
          {stats.targetHere && (
            <span className="rounded-pill bg-error-on-dark/20 px-2.5 py-0.5 text-error-on-dark">
              target is on this page ◦
            </span>
          )}
          <span className="text-text-on-dark-muted">
            {loading ? "loading…" : `${stats.n} legal links`}
          </span>
        </span>
      </header>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-[18px] bg-surface-well">
        {html === null ? (
          <p className="p-6 text-text-on-light-muted">loading the start article…</p>
        ) : (
          <ArticleFrame
            html={html}
            title={title}
            targetTitle={game.targetTitle}
            interactive={racing}
            onMove={onMove}
            onCandidates={(n, targetHere) => setStats({ n, targetHere })}
          />
        )}
        {!racing && html !== null && (
          /* Frozen, per FRONTEND.md §7. This needs to be UNMISSABLE, not
             tasteful: it is the frame an audience sees at the instant someone
             wins, and a 10% tint (what this was) reads as "nothing happened"
             from across a room. In the real app App.tsx routes `finished` to
             <Results/> immediately, so this shows for one frame on a win — but
             it is also the steady state during `arming` and `countdown`, when
             the player must be visibly unable to start early. */
          <div
            className="absolute inset-0 grid place-items-center bg-card-green/55 backdrop-blur-[2px]"
            aria-hidden
          >
            <span className="rounded-pill bg-card-green px-5 py-2 font-display text-xl text-text-on-dark shadow-card">
              {game.phase === "finished"
                ? "race over"
                : game.phase === "countdown"
                  ? (game.countdown ?? "") || "get ready"
                  : "get ready"}
            </span>
          </div>
        )}
      </div>

      {error && (
        <p className="px-1 pt-2 text-sm text-error-on-dark" role="status">
          {error}
        </p>
      )}

      <footer className="px-1 pt-3">
        <PathTrail trail={game.playerTrail} hops={game.playerHops} label="you" />
      </footer>
    </section>
  );
}
export default PlayerPanel;
