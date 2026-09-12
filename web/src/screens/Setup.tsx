import { useEffect, useState } from "react";
import type { Difficulty } from "../agent/types";
import { Card } from "../components/Card";
import { DifficultySegment } from "../components/DifficultySegment";
import { InlineError } from "../components/InlineError";
import { Pill } from "../components/Pill";
import { TitleInput } from "../components/TitleInput";
import { TopNav } from "../components/TopNav";
import { randomPair } from "../lib/pairs";
import { titlesMatch, validateTitles } from "../lib/wikiApi";
import { startRace, useGame } from "../state/gameStore";

export function Setup() {
  const game = useGame();
  const [difficulty, setDifficulty] = useState<Difficulty>(game.difficulty);
  const [seed] = useState(() =>
    game.lastStart && game.lastTarget
      ? { start: game.lastStart, target: game.lastTarget }
      : randomPair(game.difficulty),
  );
  const [start, setStart] = useState(seed.start);
  const [target, setTarget] = useState(seed.target);
  const [startErr, setStartErr] = useState<string | null>(null);
  const [targetErr, setTargetErr] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [checking, setChecking] = useState(false);
  const busy = game.phase === "validating";

  useEffect(() => {
    setStartErr(null);
    setTargetErr(null);
    setReady(false);
    const a = start.trim();
    const b = target.trim();
    if (!a || !b) return;
    const handle = window.setTimeout(() => {
      setChecking(true);
      void validateTitles(a, b)
        .then((v) => {
          if (v.ok) {
            setStart(v.start);
            setTarget(v.target);
            setReady(true);
          } else if (v.field === "start") {
            setStartErr(v.msg);
          } else if (v.field === "target") {
            setTargetErr(v.msg);
          } else {
            setStartErr(v.msg);
            setTargetErr(v.msg);
          }
        })
        .catch((err: unknown) => {
          setStartErr(err instanceof Error ? err.message : "Lookup failed.");
        })
        .finally(() => setChecking(false));
    }, 350);
    return () => window.clearTimeout(handle);
  }, [start, target]);

  function onTier(tier: Difficulty) {
    setDifficulty(tier);
    const pair = randomPair(tier, { start, target, hops: 2, fanout: 0 });
    setStart(pair.start);
    setTarget(pair.target);
  }

  function onRandomize() {
    const pair = randomPair(difficulty, { start, target, hops: 2, fanout: 0 });
    setStart(pair.start);
    setTarget(pair.target);
  }

  const canStart =
    ready && !checking && !busy && !titlesMatch(start, target) && !startErr && !targetErr;

  return (
    <div className="min-h-screen p-6 font-body">
      <TopNav />
      <div className="mt-16 flex justify-center">
        <Card
          tone="green"
          radius="hero"
          className="flex w-[min(630px,92vw)] flex-col p-10"
        >
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight">
            wikirace
            <br />
            the agent
          </h1>
          <p className="mt-6 max-w-md text-lg leading-snug text-text-on-dark-muted">
            Race a web agent from one Wikipedia article to another. First to land
            on the target wins.
          </p>

          <div className="mt-auto pt-12">
            <p className="text-sm text-text-on-dark-muted">Where to where?</p>
            <div className="mt-4 space-y-4">
              <DifficultySegment
                value={difficulty}
                onChange={onTier}
                disabled={busy}
              />
              <TitleInput
                label="Start"
                value={start}
                onChange={setStart}
                error={startErr}
                disabled={busy}
              />
              <TitleInput
                label="Target"
                value={target}
                onChange={setTarget}
                error={targetErr}
                disabled={busy}
              />
            </div>
            <InlineError message={game.setupError} onDark />
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Pill variant="ghost" size="sm" onClick={onRandomize} disabled={busy}>
                Randomize
              </Pill>
              <Pill
                variant="black"
                disabled={!canStart}
                onClick={() => void startRace({ start, target, difficulty })}
              >
                {busy ? "Checking…" : "Start Race"}
              </Pill>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
