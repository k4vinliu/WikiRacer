import { useSyncExternalStore } from "react";
import { makeFeed, type FeedHandle } from "../agent";
import type {
  AgentEvent,
  Difficulty,
  Pair,
  RaceReason,
  Winner,
} from "../agent/types";
import { findPair, randomPair } from "../lib/pairs";
import { fetchArticle, titlesMatch, validateTitles, type Article } from "../lib/wikiApi";

export type Phase =
  | "setup"
  | "validating"
  | "arming"
  | "countdown"
  | "racing"
  | "finished"
  | "abandoned";

export type TrailHop = {
  title: string;
  anchorText: string;
  at: number;
};

export type GameSnapshot = {
  phase: Phase;
  difficulty: Difficulty;
  pair: Pair | null;
  startTitle: string;
  targetTitle: string;
  lastStart: string;
  lastTarget: string;
  playerTrail: TrailHop[];
  agentTrail: TrailHop[];
  playerHops: number;
  agentHops: number;
  t0: number | null;
  winner: Winner;
  reason: RaceReason | null;
  elapsedMsAtFinish: number | null;
  marginMs: number | null;
  liveUrl: string | null;
  sessionId: string | null;
  agentEvents: AgentEvent[];
  agentStatus: "idle" | "thinking" | "racing" | "gave_up" | "won" | "error";
  agentMessage: string | null;
  countdown: number | null;
  setupError: string | null;
  startArticle: Article | null;
  findTarget: boolean;
  maxHops: number;
};

const LIVE_KEY = "wikirace.live";
const ARM_MS = 20_000;
const MAX_HOPS = 25;

function emptySnapshot(over: Partial<GameSnapshot> = {}): GameSnapshot {
  return {
    phase: "setup",
    difficulty: "medium",
    pair: null,
    startTitle: "",
    targetTitle: "",
    lastStart: "",
    lastTarget: "",
    playerTrail: [],
    agentTrail: [],
    playerHops: 0,
    agentHops: 0,
    t0: null,
    winner: "none",
    reason: null,
    elapsedMsAtFinish: null,
    marginMs: null,
    liveUrl: null,
    sessionId: null,
    agentEvents: [],
    agentStatus: "idle",
    agentMessage: null,
    countdown: null,
    setupError: null,
    startArticle: null,
    findTarget: true,
    maxHops: MAX_HOPS,
    ...over,
  };
}

function wasLive(): boolean {
  try {
    return sessionStorage.getItem(LIVE_KEY) === "1";
  } catch {
    return false;
  }
}

function setLive(on: boolean) {
  try {
    if (on) sessionStorage.setItem(LIVE_KEY, "1");
    else sessionStorage.removeItem(LIVE_KEY);
  } catch {
    /* private mode */
  }
}

let state: GameSnapshot = emptySnapshot({
  phase: wasLive() ? "abandoned" : "setup",
});

const listeners = new Set<() => void>();
let feed: FeedHandle | null = null;
let unsubFeed: (() => void) | null = null;
let startGen = 0;
let painted = false;
let agentReady = false;
let playerFinishAt: number | null = null;
let agentFinishAt: number | null = null;
const seenSeq = new Set<number>();

function emit() {
  for (const l of listeners) l();
}

function patch(partial: Partial<GameSnapshot>) {
  state = { ...state, ...partial };
  emit();
}

export function getGame(): GameSnapshot {
  return state;
}

export function subscribeGame(onStore: () => void): () => void {
  listeners.add(onStore);
  return () => {
    listeners.delete(onStore);
  };
}

export function useGame(): GameSnapshot {
  return useSyncExternalStore(subscribeGame, getGame, getGame);
}

function teardownFeed() {
  unsubFeed?.();
  unsubFeed = null;
  feed?.stop();
  feed = null;
}

function resetRunFlags() {
  painted = false;
  agentReady = false;
  playerFinishAt = null;
  agentFinishAt = null;
  seenSeq.clear();
}

async function sleep(ms: number, gen: number) {
  await new Promise((r) => setTimeout(r, ms));
  return gen === startGen;
}

function tryAnnounce() {
  if (state.phase === "finished") return;
  if (state.winner !== "none") return;
  if (playerFinishAt == null && agentFinishAt == null) return;

  let winner: Winner = "none";
  let at = 0;
  if (playerFinishAt != null && agentFinishAt != null) {
    winner = playerFinishAt <= agentFinishAt ? "human" : "bot";
    at = Math.min(playerFinishAt, agentFinishAt);
    patch({ marginMs: Math.abs(playerFinishAt - agentFinishAt) });
  } else if (playerFinishAt != null) {
    winner = "human";
    at = playerFinishAt;
  } else if (agentFinishAt != null) {
    winner = "bot";
    at = agentFinishAt;
  }

  setLive(false);
  teardownFeed();
  patch({
    phase: "finished",
    winner,
    reason: "won",
    elapsedMsAtFinish: at,
    agentStatus: winner === "bot" ? "won" : state.agentStatus,
  });
}

function noteReach(who: "human" | "bot", at: number) {
  if (who === "human") {
    if (playerFinishAt == null) playerFinishAt = at;
  } else if (agentFinishAt == null) {
    agentFinishAt = at;
  }
  if (playerFinishAt != null && agentFinishAt != null) {
    patch({ marginMs: Math.abs(playerFinishAt - agentFinishAt) });
  }
  tryAnnounce();
}

function onAgentEvent(e: AgentEvent) {
  if (seenSeq.has(e.seq)) return;
  seenSeq.add(e.seq);
  patch({ agentEvents: [...state.agentEvents, e] });

  if (e.t === "ready") {
    agentReady = true;
    patch({ liveUrl: e.live_url || null, sessionId: e.session_id });
    return;
  }
  if (e.t === "thinking") {
    patch({ agentStatus: "thinking" });
    return;
  }
  if (e.t === "pick") {
    patch({ agentStatus: "racing" });
    return;
  }
  if (e.t === "arrive") {
    const at = e.at;
    const hop: TrailHop = {
      title: e.article,
      anchorText: "",
      at,
    };
    const lastPick = [...state.agentEvents].reverse().find((x) => x.t === "pick");
    if (lastPick && lastPick.t === "pick") hop.anchorText = lastPick.anchor_text;
    const trail =
      state.agentTrail.length === 0
        ? [{ title: state.startTitle, anchorText: "", at: 0 }, hop]
        : [...state.agentTrail, hop];
    patch({
      agentTrail: trail,
      agentHops: Math.max(0, trail.length - 1),
      agentStatus: "racing",
    });
    if (titlesMatch(e.article, state.targetTitle)) noteReach("bot", at);
    return;
  }
  if (e.t === "done") {
    if (e.reason === "won") {
      if (titlesMatch(state.agentTrail.at(-1)?.title ?? "", state.targetTitle)) {
        noteReach("bot", e.at);
      }
      return;
    }
    if (e.reason === "hop_limit_reached" || e.reason === "dead_end") {
      patch({
        agentStatus: "gave_up",
        agentMessage: e.message ?? `gave up after ${e.hops} hops`,
        reason: state.winner === "none" ? e.reason : state.reason,
      });
      return;
    }
    if (e.reason === "error") {
      setLive(false);
      teardownFeed();
      patch({
        phase: "finished",
        winner: "none",
        reason: "error",
        elapsedMsAtFinish: state.t0 != null ? performance.now() - state.t0 : e.at,
        agentStatus: "error",
        agentMessage: e.message ?? "Race ended early.",
      });
    }
    return;
  }
  if (e.t === "error") {
    patch({
      agentStatus: "error",
      agentMessage: e.message,
    });
    if (e.fatal) {
      setLive(false);
      teardownFeed();
      patch({
        phase: "finished",
        winner: "none",
        reason: "error",
        elapsedMsAtFinish: state.t0 != null ? performance.now() - state.t0 : 0,
      });
    }
  }
}

function failArm(message: string) {
  setLive(false);
  teardownFeed();
  resetRunFlags();
  patch({
    phase: "setup",
    setupError: message,
    countdown: null,
    t0: null,
    agentStatus: "idle",
    liveUrl: null,
  });
}

export async function startRace(input: {
  start: string;
  target: string;
  difficulty: Difficulty;
}): Promise<void> {
  const gen = ++startGen;
  resetRunFlags();
  patch({
    phase: "validating",
    difficulty: input.difficulty,
    setupError: null,
    findTarget: input.difficulty !== "easy",
    winner: "none",
    reason: null,
    elapsedMsAtFinish: null,
    marginMs: null,
    agentEvents: [],
    agentMessage: null,
    agentStatus: "idle",
    playerTrail: [],
    agentTrail: [],
    playerHops: 0,
    agentHops: 0,
  });

  let start = input.start;
  let target = input.target;
  try {
    const v = await validateTitles(input.start, input.target);
    if (gen !== startGen) return;
    if (!v.ok) {
      patch({ phase: "setup", setupError: v.msg });
      return;
    }
    start = v.start;
    target = v.target;
  } catch (err) {
    if (gen !== startGen) return;
    failArm(err instanceof Error ? err.message : "Could not validate titles.");
    return;
  }

  const pair =
    findPair(start, target, input.difficulty) ?? {
      start,
      target,
      hops: 3 as const,
      atLeast: true as const,
      fanout: 0,
    };

  patch({
    phase: "arming",
    pair,
    startTitle: start,
    targetTitle: target,
    lastStart: start,
    lastTarget: target,
    startArticle: null,
    liveUrl: null,
    sessionId: null,
  });
  setLive(true);

  try {
    const articleP = fetchArticle(start).then((article) => {
      if (gen !== startGen) return;
      painted = true;
      patch({ startArticle: article });
    });

    feed = makeFeed(pair);
    await feed.arm({
      start,
      target,
      difficulty: input.difficulty,
      findTarget: input.difficulty !== "easy",
    });
    if (gen !== startGen) return;
    unsubFeed = feed.subscribe(onAgentEvent);

    const readyP = (async () => {
      const t0 = performance.now();
      while (!agentReady || !painted) {
        if (gen !== startGen) return;
        if (performance.now() - t0 > ARM_MS) {
          throw new Error("Arming timed out. The agent didn't come ready in time.");
        }
        await new Promise((r) => setTimeout(r, 50));
      }
    })();

    await Promise.all([articleP, readyP]);
    if (gen !== startGen) return;

    for (const n of [3, 2, 1]) {
      patch({ phase: "countdown", countdown: n });
      if (!(await sleep(1000, gen))) return;
    }
    patch({ countdown: 0 });
    if (!(await sleep(350, gen))) return;

    const t0 = performance.now();
    const startHop = { title: start, anchorText: "", at: 0 };
    patch({
      phase: "racing",
      countdown: null,
      t0,
      playerTrail: [startHop],
      agentTrail: [startHop],
      playerHops: 0,
      agentHops: 0,
      agentStatus: "racing",
    });
    await feed.go();
  } catch (err) {
    if (gen !== startGen) return;
    failArm(err instanceof Error ? err.message : "Arming failed.");
  }
}

export function markStartPainted(): void {
  painted = true;
}

export function playerNavigated(move: { title: string; anchorText: string }): void {
  if (state.phase !== "racing" || state.t0 == null) return;
  const at = performance.now() - state.t0;
  const hop: TrailHop = { title: move.title, anchorText: move.anchorText, at };
  const trail = [...state.playerTrail, hop];
  patch({
    playerTrail: trail,
    playerHops: Math.max(0, trail.length - 1),
  });
  if (titlesMatch(move.title, state.targetTitle)) noteReach("human", at);
}

export function raceAgain(): void {
  startGen += 1;
  teardownFeed();
  resetRunFlags();
  setLive(false);
  patch(
    emptySnapshot({
      difficulty: state.difficulty,
      lastStart: state.startTitle || state.lastStart,
      lastTarget: state.targetTitle || state.lastTarget,
      pair: state.pair,
    }),
  );
}

export function newArticles(): void {
  startGen += 1;
  teardownFeed();
  resetRunFlags();
  setLive(false);
  const pair = randomPair(state.difficulty);
  patch(
    emptySnapshot({
      difficulty: state.difficulty,
      lastStart: pair.start,
      lastTarget: pair.target,
      pair,
    }),
  );
}

export function dismissAbandoned(): void {
  startGen += 1;
  teardownFeed();
  resetRunFlags();
  setLive(false);
  try {
    void fetch("http://127.0.0.1:8848/stop", { method: "POST" }).catch(() => undefined);
  } catch {
    /* server may not be up */
  }
  patch(emptySnapshot({ difficulty: state.difficulty }));
}
