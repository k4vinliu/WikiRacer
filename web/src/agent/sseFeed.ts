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
      // EventSource retries forever. Announce once, and only after we had a live
      // stream — otherwise the first connecting blip becomes a false disconnect.
      source.onerror = () => {
        if (closed || announcedDisconnect || !opened) return;
        announcedDisconnect = true;
        on({
          seq: Number.MAX_SAFE_INTEGER,
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
