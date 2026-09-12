/**
 * Lane A phase switch. Race.tsx (Lane B) is not imported — until it exists we
 * render a stand-in that still exercises the referee, TimerBar, and mockFeed.
 */
import { useState } from "react";
import { Pill } from "./components/Pill";
import { TimerBar } from "./components/TimerBar";
import { playerNavigated, useGame } from "./state/gameStore";
import { Abandoned } from "./screens/Abandoned";
import { Results } from "./screens/Results";
import { Setup } from "./screens/Setup";

function RaceStandIn() {
  const game = useGame();
  const [hop, setHop] = useState("");
  const you = game.playerTrail.at(-1)?.title ?? game.startTitle;
  const agent = game.agentTrail.at(-1)?.title ?? game.startTitle;

  function jump() {
    const title = hop.trim();
    if (!title || game.phase !== "racing") return;
    playerNavigated({ title, anchorText: title });
    setHop("");
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <section className="flex min-h-0 flex-1 flex-col bg-surface-well p-6">
        <p className="text-sm text-text-on-light-muted">
          YOU · {you}
        </p>
        <p className="mt-2 text-text-on-light">
          Article renderer is Lane B. Until it lands, jump by canonical title.
          Type the target and go to win.
        </p>
        <div className="mt-6 flex flex-wrap items-end gap-3">
          <label className="block text-left">
            <span className="text-sm text-text-on-light-muted">Hop to</span>
            <input
              value={hop}
              onChange={(e) => setHop(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") jump();
              }}
              disabled={game.phase !== "racing"}
              className="mt-1 block rounded-pill bg-surface-grey px-4 py-2 text-text-on-light outline-none"
            />
          </label>
          <Pill variant="black" size="sm" disabled={game.phase !== "racing"} onClick={jump}>
            Jump
          </Pill>
        </div>
        <ol className="mt-6 list-decimal pl-5 text-text-on-light">
          {game.playerTrail.map((h, i) => (
            <li key={`${h.title}-${i}`}>{h.title}</li>
          ))}
        </ol>
      </section>
      <section className="flex min-h-0 flex-1 flex-col bg-card-green p-6 text-text-on-dark on-dark">
        <p className="text-sm text-text-on-dark-muted">
          AGENT · {agent}
          {game.liveUrl ? " · live" : " · mock"}
        </p>
        {game.liveUrl ? (
          <iframe
            title="Agent live view"
            src={`${game.liveUrl}${game.liveUrl.includes("?") ? "&" : "?"}interactive=false`}
            className="mt-3 aspect-video w-full rounded-card bg-accent-black"
          />
        ) : (
          <div className="mt-3 flex aspect-video w-full items-center justify-center rounded-card bg-card-green-soft text-text-on-dark-muted">
            Mock agent — no Steel session
          </div>
        )}
        <ol className="mt-4 min-h-0 flex-1 space-y-1 overflow-auto text-sm">
          {game.agentEvents.map((e) => (
            <li key={e.seq}>
              {e.t === "thinking" ? (
                <span>◔ thinking · {e.article} · {e.n_candidates} links</span>
              ) : null}
              {e.t === "pick" ? (
                <span>
                  {e.from} ─▶ “{e.anchor_text}”{" "}
                  <span className="text-text-on-dark-muted">{e.reason}</span>
                </span>
              ) : null}
              {e.t === "arrive" ? <span>landed {e.article}</span> : null}
              {e.t === "done" ? <span>done · {e.reason}</span> : null}
              {e.t === "error" ? <span>{e.message}</span> : null}
              {e.t === "ready" ? <span>ready</span> : null}
            </li>
          ))}
        </ol>
        {game.agentStatus === "gave_up" ? (
          <p className="mt-3 text-text-on-dark-muted">
            The agent gave up after {game.agentHops} hops. You can still win.
          </p>
        ) : null}
      </section>
    </div>
  );
}

function RaceShell() {
  const game = useGame();
  return (
    <div className="flex min-h-screen flex-col">
      <TimerBar game={game} />
      {game.phase === "arming" ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="font-display text-4xl text-text-on-light">Arming…</p>
        </div>
      ) : null}
      {game.phase === "countdown" ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="font-display tabular-slots text-[min(150px,30vw)] text-text-on-light">
            {game.countdown === 0 ? "GO" : game.countdown}
          </p>
        </div>
      ) : null}
      {game.phase === "racing" ? <RaceStandIn /> : null}
    </div>
  );
}

export default function App() {
  const game = useGame();
  if (game.phase === "abandoned") return <Abandoned />;
  if (game.phase === "finished") return <Results />;
  if (game.phase === "setup" || game.phase === "validating") return <Setup />;
  return <RaceShell />;
}
