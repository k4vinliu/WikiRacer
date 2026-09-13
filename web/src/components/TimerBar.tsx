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
        {/* The player's hop COUNT, with no denominator.
            `maxHops` is the AGENT's server-enforced budget (speedrun/server.py
            applies it to AgentRace only). Nothing caps the human -- there is no
            maxHops check in playerNavigated or PlayerPanel -- so rendering
            "HOP {playerHops}/{maxHops}" advertised a limit the player does not
            have. At the default 25 that is merely misleading; with the
            `?max_hops=N` param the header reads "RACING · HARD · HOP 4/3"
            (rendered and confirmed), because §7 keeps the human clicking after
            the agent's budget runs out. The agent's budget still surfaces where
            it means something: the give-up line right below, and AgentPanel. */}
        <p className="text-sm tracking-wide text-text-on-dark-muted">
          {phaseLabel} · {game.difficulty.toUpperCase()} · HOP {game.playerHops}
        </p>
        {game.agentStatus === "gave_up" ? (
          <p className="text-sm text-text-on-dark-muted">
            The agent gave up after {game.agentHops} hops
          </p>
        ) : null}
      </div>
      <div className="text-[92px] leading-none">
        <TimerDigits ms={ms} />
      </div>
      <div className="min-w-0 flex-1 text-right">
        <p className="truncate text-lg text-text-on-dark">
          {game.startTitle} <span className="text-text-on-dark-muted">──▶</span> {game.targetTitle}
        </p>
        <p className="text-sm text-text-on-dark-muted">Reach: {game.targetTitle}</p>
      </div>
    </header>
  );
}
