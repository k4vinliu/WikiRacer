/**
 * The Race screen. Lane B. FRONTEND.md §4.3.
 *
 * Two columns, the right one stacked. The live view is the only element with a
 * fixed aspect ratio (16:9), and stacking is the only arrangement that gives it
 * a WIDE 16:9 slot rather than a tall narrow one. Player gets the larger column
 * because 672px of running text is the floor for a scannable article (42rem at
 * 17.5px ≈ 78ch) and 896px leaves headroom for infoboxes and wide tables.
 *
 * Deliberately NOT a HUD. One 112px header row: phase and hops left, the timer
 * centred as the single focal element, the route right. An earlier draft of the
 * spec had a 128px header with four rows of keyboard hints; that fights the
 * "soft, minimal, editorial, lots of negative space" language the design asks
 * for, so hints live behind the nav instead.
 *
 * Assumes 1920x1080, Chrome fullscreen, 100% zoom — a hard prerequisite, so
 * rehearse at the real resolution (FRONTEND.md CP4).
 */
import { useState } from "react";

import AgentPanel from "../components/AgentPanel";
import PlayerPanel from "../components/PlayerPanel";
import TargetBadge from "../components/TargetBadge";
import { TimerBar } from "../components/TimerBar";
import { useGame } from "../state/gameStore";

export function Race() {
  const game = useGame();
  // "Is the winning link on the page the player is looking at?" is discovered
  // inside PlayerPanel (ArticleFrame reports it), but it is displayed in the
  // header, so it is lifted here rather than duplicated.
  const [targetHere, setTargetHere] = useState(false);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="on-dark grid h-28 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-6 bg-card-green px-6">
        <div className="flex items-baseline gap-4 text-sm uppercase tracking-wider text-text-on-dark-muted">
          <span>{game.phase}</span>
          <span>{game.difficulty}</span>
          <span>
            you {game.playerHops} · agent {game.agentHops}/{game.maxHops}
          </span>
        </div>

        <div className="justify-self-center">
          <TimerBar game={game} />
        </div>

        <div className="justify-self-end">
          <TargetBadge target={game.targetTitle} present={targetHere} />
        </div>
      </header>

      <main className="flex min-h-0 flex-1 gap-4 p-5">
        <div className="flex min-h-0 w-[896px] shrink-0">
          <PlayerPanel onTargetPresence={setTargetHere} />
        </div>
        <div className="flex min-h-0 flex-1">
          <AgentPanel />
        </div>
      </main>
    </div>
  );
}
export default Race;
