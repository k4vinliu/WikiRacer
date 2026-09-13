/**
 * The agent pane must never claim the agent is fake while it is real. Lane B.
 *
 * `--page-source http` is FRONTEND.md §9.3 lever 2: the thing we run when Steel
 * is down. In that mode `ready.live_url` is `""`, so there is no browser to
 * embed -- but Claude really is picking links off real Wikipedia. The first
 * version of this pane captioned that "mock feed -- no Steel session", which on
 * a projector tells a judge the demo is fake at the one moment it is not.
 *
 * These tests pin the three states apart: live view, real-but-no-view, mock.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentPanel from "./AgentPanel";
import type { GameSnapshot } from "../state/gameStore";

const isRealAgent = vi.fn(() => false);
vi.mock("../agent", () => ({ isRealAgent: () => isRealAgent() }));

const snapshot = (over: Partial<GameSnapshot> = {}) =>
  ({
    liveUrl: null,
    sessionId: null,
    agentStatus: "racing",
    agentEvents: [],
    agentTrail: [],
    agentHops: 0,
    agentMessage: null,
    ...over,
  }) as unknown as GameSnapshot;

let game = snapshot();
vi.mock("../state/gameStore", () => ({ useGame: () => game }));

afterEach(() => {
  isRealAgent.mockReturnValue(false);
  game = snapshot();
});

describe("AgentPanel's live-view caption", () => {
  it("says 'live' and embeds the player when there is a live URL", () => {
    game = snapshot({ liveUrl: "https://api.steel.dev/v1/sessions/abc/player" });
    render(<AgentPanel />);

    expect(screen.getByText("live")).toBeTruthy();
    const frame = screen.getByTitle("Agent's browser, live") as HTMLIFrameElement;
    // readOnly() must pin both params: without interactive=false the audience
    // could click inside the agent's real browser.
    expect(frame.src).toContain("interactive=false");
    expect(frame.src).toContain("hideOverlay=true");
  });

  it("does NOT say 'mock' when the real agent is racing without a browser", () => {
    isRealAgent.mockReturnValue(true);
    game = snapshot({ liveUrl: null });
    render(<AgentPanel />);

    expect(screen.queryByTitle("Agent's browser, live")).toBeNull();
    expect(screen.getByText("no live view")).toBeTruthy();
    // The whole point. Any copy in this state that calls the agent a mock is a
    // regression, however it is worded.
    expect(document.body.textContent?.toLowerCase()).not.toContain("mock");
    expect(document.body.textContent).toContain("still really racing");
  });

  it("does say 'mock feed' when the feed really is the mock", () => {
    isRealAgent.mockReturnValue(false);
    game = snapshot({ liveUrl: null });
    render(<AgentPanel />);

    expect(screen.getByText("mock feed")).toBeTruthy();
    expect(document.body.textContent).toContain("driven by the mock feed");
  });
});
