import { useEffect, useState } from "react";
import type { Difficulty } from "../agent/types";
import { Card } from "../components/Card";
import { DifficultySegment } from "../components/DifficultySegment";
import { InlineError } from "../components/InlineError";
import { Pill } from "../components/Pill";
import { TitleInput } from "../components/TitleInput";
import { HowItWorksDialog } from "../components/TopNav";
import { randomPair } from "../lib/pairs";
import { titlesMatch, validateTitles } from "../lib/wikiApi";
import { startRace, useGame } from "../state/gameStore";

const outlinePill =
  "!bg-transparent !text-text-on-light !ring-1 !ring-inset !ring-text-on-light/20 hover:!bg-surface-grey";

function Mark() {
  return (
    <div className="grid grid-cols-5 gap-1" aria-hidden>
      <span className="size-3.5 rounded-[3px] bg-card-green" />
      <span className="size-3.5 rounded-[3px] bg-surface-grey-dark" />
      <span className="size-3.5 rounded-[3px] bg-card-green-soft" />
      <span className="size-3.5 rounded-[3px] bg-card-green" />
      <span className="size-3.5 rounded-[3px] bg-accent-black" />
    </div>
  );
}

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
  const [help, setHelp] = useState(false);
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

  const today = new Date().toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="flex min-h-screen flex-col items-center px-6 py-10 font-body text-text-on-light">
      <div className="flex w-full max-w-[420px] flex-1 flex-col items-center justify-center text-center">
        <Mark />
        <h1 className="mt-8 font-display text-[4.25rem] leading-none tracking-tight">
          Wikirace
        </h1>
        <p className="mt-6 max-w-[20rem] text-[1.65rem] font-medium leading-snug">
          Race an AI across Wikipedia. First to the target article wins.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Pill variant="ghost" className={outlinePill} onClick={() => setHelp(true)}>
            How it works
          </Pill>
          <Pill
            variant="black"
            disabled={!canStart}
            onClick={() => void startRace({ start, target, difficulty })}
          >
            {busy ? "Checking…" : "Play"}
          </Pill>
        </div>

        <p className="mt-10 text-[1.35rem] font-medium leading-snug">{today}</p>
        <p className="mt-1 text-lg capitalize text-text-on-light-muted">
          {difficulty}
          <span className="mx-2 text-text-on-light-muted">·</span>
          {start || "…"}
          <span className="mx-1.5 text-text-on-light-muted">→</span>
          {target || "…"}
        </p>
      </div>

      <div className="mt-8 w-full max-w-[520px] space-y-4 pb-6">
        <Card tone="green" radius="card" className="p-6 text-left">
          <p className="text-sm text-text-on-dark-muted">Where to where?</p>
          <div className="mt-4 space-y-4">
            <DifficultySegment value={difficulty} onChange={onTier} disabled={busy} />
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
          <div className="mt-5">
            <Pill variant="ghost" size="sm" onClick={onRandomize} disabled={busy}>
              Randomize
            </Pill>
          </div>
        </Card>

        <button
          type="button"
          onClick={() => setHelp(true)}
          className="flex w-full items-center gap-4 rounded-card bg-surface-well px-5 py-4 text-left shadow-card"
        >
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-card-green" aria-hidden>
            <span className="size-3 rounded-sm bg-text-on-dark" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-medium">No accounts. One shared clock.</span>
            <span className="mt-0.5 block text-text-on-light-muted">
              You click Wikipedia. The agent does too. First canonical title wins.
            </span>
          </span>
          <span className="text-2xl leading-none text-text-on-light-muted" aria-hidden>
            ›
          </span>
        </button>
      </div>

      <HowItWorksDialog open={help} onClose={() => setHelp(false)} />
    </div>
  );
}
