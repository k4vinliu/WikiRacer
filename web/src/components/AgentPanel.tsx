/**
 * The agent's half. Lane B. FRONTEND.md §2.5 / §4.3.
 *
 * Shows Steel's live view PROMINENTLY, per the team's decision — not a toggle,
 * not our own re-render of the same article. Verified embeddable: the player
 * endpoint returns HTTP 200 with NO x-frame-options and NO CSP.
 *
 * `?interactive=false` is load-bearing: without it the audience could click
 * inside the agent's real browser. `?hideOverlay=true` drops Steel's own chrome.
 * Two params that do NOT exist and must not be added: `theme=light` and
 * `showControls=false` — verified zero occurrences in the served file.
 *
 * The trade-off we accepted: this pane cannot visually match the player's, so
 * parity is structural instead — identical card, radius and header treatment,
 * equal visual weight.
 */
import AgentLog from "./AgentLog";
import PathTrail from "./PathTrail";
import { useGame } from "../state/gameStore";

const readOnly = (url: string) => {
  try {
    const u = new URL(url);
    u.searchParams.set("interactive", "false");
    u.searchParams.set("hideOverlay", "true");
    return u.toString();
  } catch {
    return url;
  }
};

const STATUS: Record<string, string> = {
  idle: "waiting",
  thinking: "thinking",
  racing: "browsing",
  gave_up: "gave up",
  won: "reached the target",
  error: "error",
};

export function AgentPanel() {
  const game = useGame();
  const live = game.liveUrl ? readOnly(game.liveUrl) : null;

  return (
    <div className="flex min-h-0 w-full flex-col gap-4">
      <section className="on-dark flex min-h-0 flex-col rounded-card bg-card-green p-4 shadow-card">
        <header className="flex items-baseline justify-between gap-3 px-1 pb-3">
          <h2 className="font-medium text-text-on-dark">
            <span className="text-text-on-dark-muted">agent&rsquo;s browser · </span>
            {STATUS[game.agentStatus] ?? game.agentStatus}
          </h2>
          <span className="shrink-0 text-sm text-text-on-dark-muted">
            {live ? "live" : "mock feed — no Steel session"}
          </span>
        </header>

        {/* Exact 16:9, the only fixed-aspect element on the screen and the
            reason the right column is stacked rather than a third column. */}
        <div className="relative aspect-video w-full overflow-hidden rounded-[18px] bg-surface-well">
          {live ? (
            <iframe
              src={live}
              title="Agent's browser, live"
              sandbox="allow-scripts allow-same-origin"
              allow="autoplay"
              className="absolute inset-0 h-full w-full border-0"
            />
          ) : (
            <div className="absolute inset-0 grid place-items-center p-6 text-center">
              <p className="max-w-sm text-text-on-light-muted">
                No live session. The agent is being driven by the mock feed, so
                the race runs exactly the same — there is just no real browser
                to watch.
              </p>
            </div>
          )}
        </div>
      </section>

      <section className="on-dark flex min-h-0 flex-1 flex-col rounded-card bg-card-green p-4 shadow-card">
        <div className="min-h-0 flex-1">
          <AgentLog
            events={game.agentEvents}
            status={game.agentStatus}
            message={game.agentMessage}
          />
        </div>
        <footer className="px-1 pt-3">
          <PathTrail trail={game.agentTrail} hops={game.agentHops} label="agent" />
        </footer>
      </section>
    </div>
  );
}
export default AgentPanel;
