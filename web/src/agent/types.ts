/**
 * FRONTEND.md §6.1 — THE CROSS-LANE CONTRACT. FROZEN.
 *
 * This file is to the frontend what `speedrun/types.py` is to the Python side:
 * the one shape three lanes agree on so they can build without talking. Lane A
 * produces these events (from `mockFeed` or `sseFeed`), Lane A's `gameStore`
 * consumes them, Lane B renders them, and Lane C emits them from Python.
 *
 * Changing anything here is a cross-lane broadcast, not a commit. Post it in
 * chat and amend FRONTEND.md §6.1.
 *
 * `speedrun/events.py` is the Python mirror of this file. If you edit one and
 * not the other, the race silently stops adjudicating.
 */

/** FRONTEND.md §5.5. Difficulty moves two honest levers — pair distance and
 *  agent strength — and no artificial handicap. */
export type Difficulty = "easy" | "medium" | "hard";

/** The SAME three literals as `RaceResult.winner` in speedrun/types.py.
 *  Adopted verbatim on purpose: with no mapping layer, nothing can invert a
 *  result on a projector. There is no "tie" — see FRONTEND.md §2.6. */
export type Winner = "bot" | "human" | "none";

/** Why a race ended. Mirrors `RaceResult.reason`. Results renders all six
 *  (FRONTEND.md §4.4) — the original spec designed for two of them. */
export type RaceReason =
  | "won"
  | "hop_limit_reached"
  | "dead_end"
  | "human_finished_first"
  | "error";

/**
 * One thing the agent did. `seq` is monotonic from 1 and is what `sseFeed`
 * dedupes on — the server replays its whole log to every new subscriber, which
 * is load-bearing for the INITIAL connect (the browser subscribes after
 * POST /race and would otherwise miss `ready` and hang in `arming` forever).
 *
 * `at` is milliseconds since the server's race start. The referee adjudicates
 * on THESE timestamps, never on arrival order: the agent's hop happened before
 * its SSE frame arrived. See FRONTEND.md §2.6.
 */
export type AgentEvent =
  /** Steel is up and parked on the start article. The `arming` phase waits for
   *  this before the countdown, so the agent's cold start is never charged to
   *  race time. */
  | { seq: number; t: "ready"; at: number; session_id: string; live_url: string }
  /** An LLM call is in flight (~1s). The live view shows a static page during
   *  this, so the reasoning log must show motion instead. */
  | { seq: number; t: "thinking"; at: number; article: string; n_candidates: number }
  /**
   * The agent chose a link.
   *
   * `anchor_text` is REQUIRED and is not decorative. Because the agent
   * navigates rather than clicks (PLAN.md §1 locked decision), our extractor is
   * what proves the link existed — so the log has to name the anchor text as it
   * appeared on the page. It is what shows a judge the agent moved through a
   * real link. Do not drop it to save a field.
   */
  | {
      seq: number;
      t: "pick";
      at: number;
      from: string;
      to: string;
      anchor_text: string;
      reason: string;
      was_fallback: boolean;
    }
  /** The agent landed. `article` is the CANONICAL title (Python reads it from
   *  `<link rel="canonical">`), never derived from the URL — MediaWiki serves
   *  redirects in place. This is the event the win check runs on. */
  | { seq: number; t: "arrive"; at: number; article: string; hop: number }
  /** Terminal for the AGENT only. `hop_limit_reached` and `dead_end` do NOT end
   *  the race — the human keeps racing and can still win. FRONTEND.md §7. */
  | {
      seq: number;
      t: "done";
      at: number;
      reason: Exclude<RaceReason, "human_finished_first">;
      hops: number;
      message?: string;
    }
  /** `fatal: false` is recoverable (a dropped stream, a retried API call) and
   *  must NOT end the human's race. */
  | { seq: number; t: "error"; at: number; message: string; fatal: boolean };

export type AgentEventType = AgentEvent["t"];

/**
 * The swap point. This interface is the reason two of three lanes are unblocked
 * from minute 20 and the reason the demo survives Steel dying at 11pm: the UI
 * cannot tell a scripted `mockFeed` from a live `sseFeed`.
 *
 * Implementations: `agent/mockFeed.ts` (Lane A) and `agent/sseFeed.ts` (Lane A).
 * `agent/index.ts` picks one off `?agent=real`.
 */
export interface AgentFeed {
  /** Returns an unsubscribe function. `gameStore` MUST call it on `finished`,
   *  alongside POST /stop — otherwise a won race leaks a Steel session. */
  subscribe(on: (e: AgentEvent) => void): () => void;
}

/** A start/target pair with its measured distance. See FRONTEND.md §5.4.
 *  `hops: 2` is EXACT. `hops: 3` with `atLeast` means "proven not 1 and not 2";
 *  exact depth beyond 2 was not determined, and this type says so rather than
 *  letting a guess look like a measurement. */
export interface Pair {
  start: string;
  target: string;
  hops: 2 | 3;
  atLeast?: true;
  /** The start article's legal move count — the second difficulty lever. */
  fanout: number;
}
