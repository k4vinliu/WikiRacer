/**
 * The screen the whole demo ends on. Both of these came from the first real
 * race against a live Steel agent (Soap -> Jupiter, agent won 3 hops to 9).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { GameSnapshot, TrailHop } from "../state/gameStore";
import { formatMmSs } from "../components/TimerDigits";

let game: GameSnapshot;
vi.mock("../state/gameStore", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return { ...real, useGame: () => game, raceAgain: () => {}, newArticles: () => {} };
});
const { Results } = await import("./Results");

const hop = (title: string): TrailHop => ({ title, anchorText: title.toLowerCase(), at: 0 });

const snap = (over: Partial<GameSnapshot> = {}): GameSnapshot =>
  ({
    winner: "bot",
    reason: "won",
    elapsedMsAtFinish: 14_000,
    marginMs: null,
    playerHops: 3,
    agentHops: 3,
    playerTrail: [hop("Soap"), hop("Sodium stearate")],
    agentTrail: [hop("Soap"), hop("Sodium")],
    agentStatus: "won",
    agentMessage: null,
    ...over,
  }) as unknown as GameSnapshot;

describe("Results", () => {
  it("labels the clock in a unit that matches what it prints", () => {
    game = snap({ elapsedMsAtFinish: 90_000 });
    render(<Results />);

    // The digits are MM:SS, so "Seconds to finish" was wrong: a 90s race read
    // "Seconds to finish" under "01:30".
    expect(formatMmSs(90_000)).toBe("01:30");
    expect(screen.getByText("Time to finish")).toBeTruthy();
    expect(screen.queryByText("Seconds to finish")).toBeNull();
  });

  it("keeps the actions OUT of the scrolling region when a path is long", () => {
    // A floundering human really does rack these up -- 9 hops on the first
    // live race, which pushed "Race again" below the fold on a 1080p screen.
    game = snap({
      playerHops: 9,
      playerTrail: [
        "Soap", "Sodium stearate", "Food additives", "Smoking (cooking)",
        "Smoking (disambiguation)", "Smoking", "Smoking (cooking)", "Fat", "Jupiter",
      ].map(hop),
    });
    render(<Results />);

    const again = screen.getByText("Race again");
    const paths = screen.getByText("Your path").closest("div")?.parentElement;

    expect(paths?.className).toContain("overflow-y-auto");
    // jsdom has no layout, so this is structural, not pixel-based: the actions
    // must not be inside the element that scrolls, or they scroll away with it.
    expect(paths?.contains(again)).toBe(false);
    expect(again.closest("div")?.className).toContain("shrink-0");
  });

  it("still shows every hop it was given", () => {
    game = snap({ agentTrail: ["Soap", "Sodium", "Solar System", "Jupiter"].map(hop) });
    render(<Results />);
    for (const t of ["Soap", "Sodium", "Solar System", "Jupiter"]) {
      expect(screen.getAllByText(new RegExp(t)).length).toBeGreaterThan(0);
    }
  });
});
