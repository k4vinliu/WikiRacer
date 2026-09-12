/**
 * The Race screen. Lane B. FRONTEND.md §4.3.
 *
 * Two columns, the right one stacked. The Steel live view is the only element
 * with a fixed aspect ratio (16:9), and stacking is the only arrangement that
 * gives it a WIDE 16:9 slot rather than a tall narrow one. The player gets the
 * larger column because 672px of running text is the floor for a scannable
 * article (42rem at 17.5px ≈ 78ch), and 896px leaves headroom for infoboxes and
 * wide tables.
 *
 * The header is Lane A's `<TimerBar>`, whole. It is not a timer widget — it is
 * the full 112px bar (phase · difficulty · hop on the left, digits centred,
 * route and target on the right). An earlier version of this file wrapped it in
 * a second header of my own and rendered the phase, difficulty, hops and target
 * AGAIN, so every one of them appeared twice on screen. If you need something
 * new in the header, ask Lane A for it rather than adding a parallel one here.
 *
 * Assumes 1920x1080, Chrome fullscreen, 100% zoom — a hard prerequisite, so
 * rehearse at the real resolution (FRONTEND.md CP4).
 */
import AgentPanel from "../components/AgentPanel";
import PlayerPanel from "../components/PlayerPanel";
import { TimerBar } from "../components/TimerBar";
import { useGame } from "../state/gameStore";

export function Race() {
  const game = useGame();

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TimerBar game={game} />

      <main className="flex min-h-0 flex-1 gap-4 p-5">
        <div className="flex min-h-0 w-[896px] shrink-0">
          <PlayerPanel />
        </div>
        <div className="flex min-h-0 flex-1">
          <AgentPanel />
        </div>
      </main>
    </div>
  );
}
export default Race;
