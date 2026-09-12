const W_DIGIT = "0.64em";
const W_COLON = "0.28em";

export function formatMmSs(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function TimerDigits({ ms }: { ms: number }) {
  const txt = formatMmSs(ms);
  return (
    <span className="font-display tabular-slots" aria-label={`${txt} elapsed`}>
      {[...txt].map((c, i) => (
        <span
          key={i}
          style={{
            display: "inline-block",
            width: c === ":" ? W_COLON : W_DIGIT,
            textAlign: "center",
          }}
        >
          {c}
        </span>
      ))}
    </span>
  );
}
