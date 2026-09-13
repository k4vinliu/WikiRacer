import type { AgentEvent, AgentFeed, Difficulty } from "./types";

export const AGENT_BASE = "http://127.0.0.1:8848";

export type FeedHandle = AgentFeed & {
  arm: (args: {
    start: string;
    target: string;
    difficulty: Difficulty;
    findTarget: boolean;
    maxHops?: number;
  }) => Promise<void>;
  go: () => Promise<void>;
  stop: () => void;
};

type RaceStart = { id?: string; race_id?: string; error?: string };

function errorMessage(status: number, path: string, text: string): string {
  try {
    const body = JSON.parse(text) as { error?: unknown };
    if (typeof body.error === "string" && body.error.trim()) return body.error;
  } catch {
    /* not JSON */
  }
  return `Agent server ${status} on ${path}`;
}

export function sseFeed(base = AGENT_BASE): FeedHandle {
  let raceId: string | null = null;
  let source: EventSource | null = null;
  let closed = false;
  const seen = new Set<number>();
  // Locally-generated notices (not from the server) get their own seq space.
  // It has to be UNIQUE per notice and can never collide with a real frame:
  // `seq` is both gameStore's dedupe key (gameStore.ts:238) and AgentLog's React
  // `key`. The old code hard-coded Number.MAX_SAFE_INTEGER, so the referee
  // swallowed every notice after the first even if the feed re-sent one.
  // Server seqs are positive and monotonic from 1, so negatives are always free.
  let noticeSeq = -1;

  const post = async (path: string, body?: unknown) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    try {
      const res = await fetch(`${base}${path}`, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      const text = await res.text();
      if (!res.ok) {
        throw new Error(errorMessage(res.status, path, text));
      }
      if (!text) return {};
      try {
        return JSON.parse(text) as RaceStart;
      } catch {
        return {};
      }
    } finally {
      clearTimeout(timer);
    }
  };

  return {
    async arm({ start, target, difficulty, findTarget, maxHops }) {
      closed = false;
      seen.clear();
      const created = await post("/race", {
        start,
        target,
        difficulty,
        find_target: findTarget,
        ...(typeof maxHops === "number" ? { max_hops: maxHops } : {}),
      });
      raceId = created.id ?? created.race_id ?? "current";
    },

    subscribe(on: (e: AgentEvent) => void) {
      const url = `${base}/events${raceId ? `?race=${encodeURIComponent(raceId)}` : ""}`;
      source = new EventSource(url);
      let opened = false;
      let announcedDisconnect = false;
      source.onopen = () => {
        opened = true;
        // Re-arm: the latch below is PER CONNECTION, not per race. Leaving it
        // set after a recovered drop meant a later, permanent disconnect was
        // announced to nobody -- the pane kept saying "browsing" over a dead
        // agent, with a stale red row from the earlier blip sitting above newer
        // hops. Reproduced with a TCP proxy: drop, recover, drop again.
        announcedDisconnect = false;
      };
      source.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as AgentEvent;
          if (typeof data.seq !== "number" || seen.has(data.seq)) return;
          seen.add(data.seq);
          on(data);
        } catch {
          /* ignore a malformed frame */
        }
      };
      // EventSource retries forever, and fires `error` on every failed attempt
      // (measured: 3 in ~1s after one drop). So announce at most once PER
      // CONNECTION — not once per race — and only after we had a live stream,
      // otherwise the first connecting blip becomes a false disconnect. `onopen`
      // clears the latch so the next drop is reported too.
      source.onerror = () => {
        if (closed || announcedDisconnect || !opened) return;
        announcedDisconnect = true;
        on({
          seq: noticeSeq--,
          t: "error",
          at: 0,
          message: "Agent disconnected",
          fatal: false,
        });
      };
      return () => {
        closed = true;
        source?.close();
        source = null;
      };
    },

    async go() {
      if (!raceId) throw new Error("No race to start.");
      await post(`/race/${encodeURIComponent(raceId)}/go`);
    },

    stop() {
      closed = true;
      source?.close();
      source = null;
      void post("/stop").catch(() => undefined);
    },
  };
}
