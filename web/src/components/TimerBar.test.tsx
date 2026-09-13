/**
 * The projector header. The left slot is one of three things a judge reads, so
 * every number in it has to mean what it looks like it means.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TimerBar } from "./TimerBar";
import type { GameSnapshot } from "../state/gameStore";

vi.mock("../state/useClock", () => ({ useClock: () => 6000 }));

const snap = (over: Partial<GameSnapshot> = {}) =>
  ({
    phase: "racing",
    difficulty: "hard",
    playerHops: 4,
    agentHops: 3,
    maxHops: 3,
    agentStatus: "gave_up",
    t0: 0,
    elapsedMsAtFinish: null,
    startTitle: "Cat",
    targetTitle: "Nuclear weapon",
    ...over,
  }) as unknown as GameSnapshot;

describe("TimerBar's hop counter", () => {
  it("never shows the agent's budget as the player's denominator", () => {
    // `?max_hops=3` + FRONTEND.md §7 (the human keeps racing after the agent
    // gives up) used to render "HOP 4/3" -- a limit the human does not have.
    render(<TimerBar game={snap()} />);

    expect(screen.getByText(/HOP 4/)).toBeTruthy();
    expect(screen.queryByText(/4\/3/)).toBeNull();
    expect(screen.queryByText(/HOP 4\/\d/)).toBeNull();
  });

  it("does not imply a 25-hop budget on a default race either", () => {
    render(<TimerBar game={snap({ maxHops: 25, playerHops: 2, agentStatus: "racing" })} />);

    expect(screen.getByText(/HOP 2/)).toBeTruthy();
    expect(screen.queryByText(/2\/25/)).toBeNull();
  });

  it("still explains the agent's budget when it bites", () => {
    render(<TimerBar game={snap()} />);
    // The agent's real limit is what produced this line; that is where the
    // number belongs.
    expect(screen.getByText("The agent gave up after 3 hops")).toBeTruthy();
  });
});
