import type { AgentEvent, AgentFeed, Difficulty } from "./types";

export const AGENT_BASE = "http://127.0.0.1:8848";

export type FeedHandle = AgentFeed & {
  arm: (args: {
    start: string;
    target: string;
    difficulty: Difficulty;
    findTarget: boolean;
  }) => Promise<void>;
  go: () => Promise<void>;
  stop: () => void;
};

type RaceStart = { id?: string; race_id?: string };

export function sseFeed(base = AGENT_BASE): FeedHandle {
  let raceId: string | null = null;
  let source: EventSource | null = null;
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
      if (!res.ok) {
        throw new Error(`Agent server ${res.status} on ${path}`);
      }
      const text = await res.text();
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
    async arm({ start, target, difficulty, findTarget }) {
      const created = await post("/race", {
        start,
        target,
        difficulty,
        find_target: findTarget,
      });
      raceId = created.id ?? created.race_id ?? "current";
    },

    subscribe(on: (e: AgentEvent) => void) {
      const url = `${base}/events${raceId ? `?race=${encodeURIComponent(raceId)}` : ""}`;
      source = new EventSource(url);
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
      source.onerror = () => {
        on({
          seq: Number.MAX_SAFE_INTEGER,
          t: "error",
          at: 0,
          message: "Agent disconnected",
          fatal: false,
        });
      };
      return () => {
        source?.close();
        source = null;
      };
    },

    async go() {
      if (!raceId) throw new Error("No race to start.");
      await post(`/race/${encodeURIComponent(raceId)}/go`);
    },

    stop() {
      source?.close();
      source = null;
      void post("/stop").catch(() => undefined);
    },
  };
}
