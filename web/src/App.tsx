/**
 * Lane A phase switch. Race.tsx is Lane B — we only mount it.
 */
import { Race } from "./screens/Race";
import { Abandoned } from "./screens/Abandoned";
import { Results } from "./screens/Results";
import { Setup } from "./screens/Setup";
import { useGame } from "./state/gameStore";

export default function App() {
  const game = useGame();
  if (game.phase === "abandoned") return <Abandoned />;
  if (game.phase === "finished") return <Results />;
  if (game.phase === "setup" || game.phase === "validating") return <Setup />;
  return <Race />;
}
