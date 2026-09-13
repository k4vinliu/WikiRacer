import { Card } from "../components/Card";
import { Pill } from "../components/Pill";
import { TimerDigits } from "../components/TimerDigits";
import { TopNav } from "../components/TopNav";
import { newArticles, raceAgain, useGame, type TrailHop } from "../state/gameStore";

function headline(winner: string, reason: string | null): string {
  // A WINNER OUTRANKS THE AGENT'S STOPPING REASON, and the order of these
  // checks is the whole point.
  //
  // `hop_limit_reached` and `dead_end` say why the AGENT stopped. FRONTEND.md §7
  // keeps the human racing after either, so "the agent gave up" and "the human
  // won" are routinely both true -- and `tryAnnounce()` deliberately preserves
  // the agent's reason in that case. Testing `reason` first therefore printed
  // "The agent gave up" in 48px while the player who had just won looked for
  // their own result. The give-up is not lost: the stats row below still reads
  // "Agent - N hops - gave up".
  if (winner === "human") return "You won!";
  if (winner === "bot") return "Agent won!";
  if (reason === "error") return "Race ended early";
  if (reason === "hop_limit_reached") return "The agent gave up";
  if (reason === "dead_end") return "The agent hit a dead end";
  // Kept as a backstop: a reason with no winner set should still read correctly.
  if (reason === "human_finished_first") return "You won!";
  return "Race ended";
}

function Path({ label, hops }: { label: string; hops: TrailHop[] }) {
  return (
    <div>
      <p className="text-sm text-text-on-dark-muted">{label}</p>
      {hops.length === 0 ? (
        <p className="mt-1 text-text-on-dark-muted">No path.</p>
      ) : (
        <ol className="mt-1 list-decimal space-y-0.5 pl-5">
          {hops.map((h, i) => (
            <li key={`${h.title}-${i}`}>
              {h.title}
              {h.anchorText ? (
                <span className="text-text-on-dark-muted"> — “{h.anchorText}”</span>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function Results() {
  const game = useGame();
  const ms = game.elapsedMsAtFinish ?? 0;
  const title = headline(game.winner, game.reason);
  const photo =
    game.winner !== "none" && game.marginMs != null && game.marginMs < 1000
      ? `Photo finish — won by ${(game.marginMs / 1000).toFixed(1)}s`
      : null;

  return (
    // A COLUMN THAT OWNS THE VIEWPORT HEIGHT, so the card can be capped to it.
    // The paths are unbounded -- a floundering human can rack up 9+ hops (seen
    // on the first real race) -- and with no cap the card just grew until
    // "Race again" sat below the fold. The host then cannot restart between
    // demos without scrolling a projector. Headline, clock and actions are
    // pinned; only the two path columns scroll.
    <div className="flex h-screen flex-col p-6 font-body">
      <TopNav />
      <div className="mt-10 flex min-h-0 flex-1 justify-center">
        <Card
          tone="green"
          radius="hero"
          className="flex max-h-full w-[min(630px,92vw)] flex-col p-10"
        >
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight">{title}</h1>
          <div
            className="mt-8 leading-none text-text-on-dark"
            style={{ fontSize: "var(--size-result)" }}
          >
            <TimerDigits ms={ms} />
          </div>
          <p className="mt-3 text-lg text-text-on-dark-muted">
            {photo ??
              (game.reason === "error"
                ? (game.agentMessage ?? "Something stopped the race.")
                : "Time to finish")}
          </p>

          <div className="mt-8 grid grid-cols-2 gap-4 text-sm text-text-on-dark-muted">
            <p>
              You · {game.playerHops} hops
            </p>
            <p>
              Agent · {game.agentHops} hops
              {game.agentStatus === "gave_up" ? " · gave up" : ""}
            </p>
          </div>

          <div className="mt-6 grid min-h-0 flex-1 gap-6 overflow-y-auto sm:grid-cols-2">
            <Path label="Your path" hops={game.playerTrail} />
            <Path label="Agent path" hops={game.agentTrail} />
          </div>

          <div className="mt-8 flex shrink-0 flex-wrap gap-3">
            <Pill variant="black" onClick={raceAgain}>
              Race again
            </Pill>
            <Pill variant="ghost" onClick={newArticles}>
              New articles
            </Pill>
          </div>
        </Card>
      </div>
    </div>
  );
}
