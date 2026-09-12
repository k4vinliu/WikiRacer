import type { Difficulty } from "../agent/types";

const TIERS: Difficulty[] = ["easy", "medium", "hard"];

type DifficultySegmentProps = {
  value: Difficulty;
  onChange: (tier: Difficulty) => void;
  disabled?: boolean;
};

export function DifficultySegment({ value, onChange, disabled }: DifficultySegmentProps) {
  return (
    <div className="text-left">
      <p className="text-sm text-text-on-dark-muted">Difficulty</p>
      <div
        role="radiogroup"
        aria-label="Difficulty"
        className="mt-1.5 inline-flex rounded-pill bg-card-green-soft p-1"
      >
        {TIERS.map((tier) => {
          const active = tier === value;
          return (
            <button
              key={tier}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => onChange(tier)}
              className={`rounded-pill px-3.5 py-1.5 text-sm capitalize ${
                active
                  ? "bg-surface-grey text-text-on-light shadow-card"
                  : "text-text-on-dark-muted hover:text-text-on-dark"
              }`}
            >
              {tier}
            </button>
          );
        })}
      </div>
      {value === "easy" ? (
        <p className="mt-2 text-sm text-text-on-dark-muted">
          Easy — the agent doesn't look ahead
        </p>
      ) : (
        <p className="mt-2 text-sm text-text-on-dark-muted">
          Typed pairs use this tier's agent settings
        </p>
      )}
    </div>
  );
}
