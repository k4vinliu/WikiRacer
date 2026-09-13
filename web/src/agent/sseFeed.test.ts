/**
 * Disconnect reporting. Lane A's feed, hardened after an adversarial review
 * reproduced a double-drop with a TCP proxy.
 *
 * EventSource retries forever and fires `error` on every failed attempt, so the
 * notice has to be latched -- but the latch must be PER CONNECTION. Latched for
 * the whole race, a stream that blipped once and recovered could then die for
 * good in total silence: the agent pane kept reading "browsing" over a dead
 * agent, with a stale red row from the earlier blip sitting above newer hops.
 *
 * jsdom has no EventSource, so this stubs one and drives the handlers directly.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { sseFeed } from "./sseFeed";
import type { AgentEvent } from "./types";

class FakeEventSource {
  static last: FakeEventSource | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  url: string;
  // Not a parameter property: `erasableSyntaxOnly` is on in tsconfig.app.json,
  // and only `tsc -b` (npm run build) catches that, not `tsc --noEmit -p tsconfig.json`.
  constructor(url: string) {
    this.url = url;
    FakeEventSource.last = this;
  }
  close() {
    this.closed = true;
  }
  /** EventSource fires `error` once per failed retry, not once per outage. */
  failRetries(n: number) {
    for (let i = 0; i < n; i++) this.onerror?.();
  }
}

const realES = (globalThis as Record<string, unknown>).EventSource;

beforeEach(() => {
  (globalThis as Record<string, unknown>).EventSource = FakeEventSource;
  FakeEventSource.last = null;
});
afterEach(() => {
  (globalThis as Record<string, unknown>).EventSource = realES;
});

function subscribed() {
  const got: AgentEvent[] = [];
  const unsub = sseFeed("http://x").subscribe((e) => got.push(e));
  const es = FakeEventSource.last!;
  return { got, unsub, es, errors: () => got.filter((e) => e.t === "error") };
}

describe("sseFeed disconnect notices", () => {
  it("stays silent for a blip before the stream ever opened", () => {
    const { es, errors } = subscribed();
    es.failRetries(3); // never opened: this is just connecting
    expect(errors()).toHaveLength(0);
  });

  it("announces once per outage, not once per retry", () => {
    const { es, errors } = subscribed();
    es.onopen!();
    es.failRetries(3);
    expect(errors()).toHaveLength(1);
    expect(errors()[0]).toMatchObject({ message: "Agent disconnected", fatal: false });
  });

  it("announces a SECOND outage after the stream recovered", () => {
    const { es, errors } = subscribed();
    es.onopen!();
    es.failRetries(2); // drop #1
    es.onopen!(); // recovered
    es.failRetries(2); // drop #2 -- used to be swallowed forever

    expect(errors()).toHaveLength(2);
  });

  it("gives each notice a unique seq that can never collide with a server frame", () => {
    const { es, errors } = subscribed();
    es.onopen!();
    es.failRetries(1);
    es.onopen!();
    es.failRetries(1);

    const seqs = errors().map((e) => e.seq);
    // Unique, or gameStore's `seenSeq` drops the second and AgentLog duplicates
    // a React key. Negative, because server seqs are positive from 1.
    expect(new Set(seqs).size).toBe(seqs.length);
    expect(seqs.every((s) => s < 0)).toBe(true);
  });

  it("says nothing once we have deliberately closed the stream", () => {
    const { es, unsub, errors } = subscribed();
    es.onopen!();
    unsub();
    es.failRetries(2);
    expect(errors()).toHaveLength(0);
    expect(es.closed).toBe(true);
  });
});
