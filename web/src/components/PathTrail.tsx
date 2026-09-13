/** The route a racer has taken. Lane B.
 *  Shows ANCHOR TEXT, not just the title — the obligation from PLAN.md §4.D:
 *  because both racers move by activating an in-body href rather than by a
 *  proven browser click, the trail is what shows the audience the link was
 *  really on the page. */
import type { TrailHop } from "../state/gameStore";

export function PathTrail({
  trail,
  hops,
  label = "path",
}: {
  trail: TrailHop[];
  hops: number;
  label?: string;
}) {
  const shown = trail.slice(-6);
  const hidden = trail.length - shown.length;
  return (
    <div className="flex items-baseline gap-2 overflow-hidden text-base">
      <span className="shrink-0 text-text-on-dark-muted">
        {label} · {hops} {hops === 1 ? "hop" : "hops"}
      </span>
      <ol className="flex min-w-0 items-baseline gap-1.5 overflow-hidden">
        {hidden > 0 && (
          <li className="shrink-0 text-text-on-dark-muted">+{hidden} …</li>
        )}
        {shown.map((h, i) => (
          <li key={`${h.title}-${h.at}`} className="flex shrink-0 items-baseline gap-1.5">
            {i > 0 || hidden > 0 ? (
              <span aria-hidden className="text-text-on-dark-muted">→</span>
            ) : null}
            <span
              className="truncate text-text-on-dark"
              title={h.anchorText && h.anchorText !== h.title
                ? `clicked "${h.anchorText}"`
                : h.title}
            >
              {h.title}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
export default PathTrail;
