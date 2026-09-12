import { Card } from "../components/Card";
import { Pill } from "../components/Pill";
import { TimerDigits } from "../components/TimerDigits";
import { TopNav } from "../components/TopNav";
import { newArticles, raceAgain, useGame, type TrailHop } from "../state/gameStore";

function headline(winner: string, reason: string | null): string {
  if (reason === "error") return "Race ended early";
  if (reason === "hop_limit_reached") return "The agent gave up";
  if (reason === "dead_end") return "The agent hit a dead end";
  if (winner === "bot") return "Agent won!";
  if (winner === "human") return "You won!";
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
    <div className="min-h-screen p-6 font-body">
      <TopNav />
      <div className="mt-16 flex justify-center">
        <Card
          tone="green"
          radius="hero"
          className="flex w-[min(630px,92vw)] flex-col p-10"
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
                : "Seconds to finish")}
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

          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <Path label="Your path" hops={game.playerTrail} />
            <Path label="Agent path" hops={game.agentTrail} />
          </div>

          <div className="mt-10 flex flex-wrap gap-3">
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
