/**
 * The referee's terminal-reason logic, driven through the REAL store.
 *
 * FRONTEND.md §7: `hop_limit_reached` and `dead_end` do NOT end the race. The
 * agent stops, the human keeps racing, and the human can still win. That is the
 * case these tests cover, because it is the one where `winner` and `reason`
 * disagree — and `Results.headline()` reads `reason` BEFORE `winner`.
 *
 * These mount Results too, not just the store: the bug this pins is not a wrong
 * state field, it is the wrong sentence in 48px type on a projector.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentEvent } from "../agent/types";

// ---------------------------------------------------------------- mocks ----

let emit: (e: AgentEvent) => void = () => {};
const feed = {
  arm: vi.fn(async () => {}),
  go: vi.fn(async () => {}),
  stop: vi.fn(),
  subscribe: vi.fn((on: (e: AgentEvent) => void) => {
    emit = on;
    return () => {};
  }),
};
vi.mock("../agent", () => ({
  makeFeed: () => feed,
  isRealAgent: () => true,
}));

vi.mock("../lib/wikiApi", () => ({
  validateTitles: async (start: string, target: string) => ({ ok: true, start, target }),
  fetchArticle: async (title: string) => ({ title, html: "<p>x</p>", canonical: title }),
  titlesMatch: (a: string, b: string) =>
    (a ?? "").trim().toLowerCase().replace(/_/g, " ") ===
    (b ?? "").trim().toLowerCase().replace(/_/g, " "),
}));

vi.mock("../lib/pairs", () => ({
  findPair: () => undefined,
  randomPair: () => ({ start: "Cat", target: "Nuclear weapon", hops: 3, fanout: 0 }),
}));

// Imported AFTER the mocks so the store picks them up.
const { startRace, playerNavigated, getGame, raceAgain } = await import("./gameStore");
const { Results } = await import("../screens/Results");

const START = "Cat";
const TARGET = "Nuclear weapon";

/** Drive the real store from `setup` to `racing`, with the agent armed. */
async function toRacing() {
  const p = startRace({ start: START, target: TARGET, difficulty: "medium" });
  await vi.advanceTimersByTimeAsync(20); // validate -> arm -> subscribe
  emit({ seq: 1, t: "ready", at: 0, session_id: "s", live_url: "" });
  await vi.advanceTimersByTimeAsync(120); // the arming poll notices
  await vi.advanceTimersByTimeAsync(4000); // 3-2-1 + 350ms
  await p;
  expect(getGame().phase).toBe("racing");
}

beforeEach(async () => {
  vi.useFakeTimers();
  raceAgain();
  await vi.advanceTimersByTimeAsync(10);
});

describe("the agent gives up, then the human wins", () => {
  it("keeps the race alive when the agent hits the hop limit", async () => {
    await toRacing();

    emit({ seq: 2, t: "done", at: 1000, reason: "hop_limit_reached", hops: 25 });

    const g = getGame();
    // FRONTEND.md §7: the agent stopping must not end the human's race.
    expect(g.phase).toBe("racing");
    expect(g.winner).toBe("none");
    expect(g.agentStatus).toBe("gave_up");
  });

  it("declares the HUMAN the winner, and says so", async () => {
    await toRacing();
    emit({ seq: 2, t: "done", at: 1000, reason: "hop_limit_reached", hops: 25 });

    playerNavigated({ title: TARGET, anchorText: "nuclear weapons" });

    const g = getGame();
    expect(g.phase).toBe("finished");
    expect(g.winner).toBe("human");

    // THE POINT. The player just won. Results reads `reason` before `winner`,
    // so leaving the agent's give-up reason in place makes the biggest text on
    // the screen describe the agent instead of the human's win.
    render(<Results />);
    expect(screen.getByText("You won!")).toBeTruthy();
    expect(screen.queryByText("The agent gave up")).toBeNull();
  });

  it("declares the human the winner after a dead end too", async () => {
    await toRacing();
    emit({ seq: 2, t: "done", at: 900, reason: "dead_end", hops: 4 });

    playerNavigated({ title: TARGET, anchorText: "nuclear weapons" });

    expect(getGame().winner).toBe("human");
    render(<Results />);
    expect(screen.getByText("You won!")).toBeTruthy();
    expect(screen.queryByText("The agent hit a dead end")).toBeNull();
  });

  it("still explains the give-up when NOBODY reached the target", async () => {
    await toRacing();
    emit({ seq: 2, t: "done", at: 1000, reason: "hop_limit_reached", hops: 25 });

    // No player win: the store is still racing, and the agent's reason is the
    // only thing that happened. It must survive for the log and the copy.
    expect(getGame().reason).toBe("hop_limit_reached");
    expect(getGame().agentMessage).toContain("25");
  });
});
