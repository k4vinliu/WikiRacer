import type { Pair } from "../lib/pairs";
import { mockFeed } from "./mockFeed";
import { sseFeed } from "./sseFeed";
import type { FeedHandle } from "./sseFeed";

export type { FeedHandle };

/**
 * Is the app wired to the REAL Python agent (`?agent=real`), rather than the
 * scripted mock?
 *
 * Exported because "is there a live view" and "is the agent real" are two
 * different questions, and the UI got them confused. With
 * `server.py --page-source http` -- FRONTEND.md §9.3 lever 2, the lever we pull
 * when Steel is down -- there is no browser to embed, so `live_url` is `""`,
 * but the race is entirely real: real Claude, real Wikipedia, real hops. The
 * agent pane must not caption that "mock feed". See AgentPanel.
 */
export const isRealAgent = () =>
  new URLSearchParams(location.search).get("agent") === "real";

export function makeFeed(pair: Pair): FeedHandle {
  return isRealAgent() ? sseFeed() : mockFeed(pair);
}

export { mockFeed, sseFeed };
