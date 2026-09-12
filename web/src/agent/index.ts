import type { Pair } from "../lib/pairs";
import { mockFeed } from "./mockFeed";
import { sseFeed } from "./sseFeed";
import type { FeedHandle } from "./sseFeed";

export type { FeedHandle };

export function makeFeed(pair: Pair): FeedHandle {
  return new URLSearchParams(location.search).get("agent") === "real"
    ? sseFeed()
    : mockFeed(pair);
}

export { mockFeed, sseFeed };
