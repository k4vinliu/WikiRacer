import type { GameSnapshot } from "../state/gameStore";
import { useClock } from "../state/useClock";
import { TimerDigits } from "./TimerDigits";

export function TimerBar({ game }: { game: GameSnapshot }) {
  const running = game.phase === "racing";
  const ms = useClock(game.t0, running, game.elapsedMsAtFinish);
  const phaseLabel =
    game.phase === "arming"
      ? "ARMING"
      : game.phase === "countdown"
        ? "COUNTDOWN"
        : game.phase === "finished"
          ? "FINISHED"
          : "RACING";

  return (
    <header className="on-dark flex h-[112px] w-full items-center bg-card-green px-6 text-text-on-dark">
      <div className="flex min-w-0 flex-1 flex-col justify-center">
        <p className="text-base tracking-wide text-text-on-dark-muted">
          {phaseLabel} · {game.difficulty.toUpperCase()} · HOP {game.playerHops}/{game.maxHops}
        </p>
        {game.agentStatus === "gave_up" ? (
          <p className="text-base text-text-on-dark-muted">
            The agent gave up after {game.agentHops} hops
          </p>
        ) : null}
      </div>
      <div className="text-[92px] leading-none">
        <TimerDigits ms={ms} />
      </div>
      <div className="min-w-0 flex-1 text-right">
        <p className="truncate text-xl text-text-on-dark">
          {game.startTitle} <span className="text-text-on-dark-muted">──▶</span> {game.targetTitle}
        </p>
        <p className="text-base text-text-on-dark-muted">Reach: {game.targetTitle}</p>
      </div>
    </header>
  );
}
