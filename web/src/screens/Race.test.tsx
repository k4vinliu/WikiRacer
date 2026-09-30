/**
 * The race screen's agent column. Lane B's screen; this regression test was added 2026-09-13.
 *
 * jsdom has no layout engine, so this pins the one class that decides the bug. A flex item
 * defaults to min-width:auto ("never narrower than my content"). The agent's route line never
 * wraps, so near the end of a race it outgrew the right-hand column, which was then forced
 * wider, past the window edge, while the 16:9 live view grew to match. Reproduced in Chrome at
 * 1280x800: the column went from 328 to 391 px wide with 328 px of room. With min-w-0 on the
 * column (and on AgentPanel's root, pinned in AgentPanel.test.tsx) the line is clipped instead.
 */
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Race } from "./Race";
import type { GameSnapshot } from "../state/gameStore";

const game = {
  phase: "racing",
  difficulty: "medium",
  countdown: null,
  t0: 0,
  elapsedMsAtFinish: null,
  startTitle: "Lighthouse",
  targetTitle: "Dinosaur",
  startArticle: null,
  playerTrail: [],
  playerHops: 0,
  liveUrl: null,
  sessionId: null,
  agentStatus: "racing",
  agentEvents: [],
  agentTrail: [],
  agentHops: 0,
  agentMessage: null,
} as unknown as GameSnapshot;

vi.mock("../state/gameStore", () => ({
  useGame: () => game,
  markStartPainted: () => {},
  playerNavigated: () => {},
}));
vi.mock("../state/useClock", () => ({ useClock: () => 0 }));
vi.mock("../agent", () => ({ isRealAgent: () => false }));

describe("the race screen's layout", () => {
  it("lets the agent column shrink below its content", () => {
    const { container } = render(<Race />);
    const column = container.querySelector("main")?.children[1] as HTMLElement;
    expect(column.className.split(/\s+/)).toContain("min-w-0");
  });
});
