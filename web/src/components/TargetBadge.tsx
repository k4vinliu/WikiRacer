/** The persistent "where am I going" reminder. Lane B. FRONTEND.md §4.3.
 *  `present` means the target link is on the page the player is looking at —
 *  the agent gets that for free via links.find_target, so surfacing it for the
 *  human restores symmetry rather than granting an advantage. */
export function TargetBadge({
  target,
  present = false,
}: {
  target: string;
  present?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-sm uppercase tracking-wider text-text-on-dark-muted">
        reach
      </span>
      <span className="font-display text-xl text-text-on-dark">{target}</span>
      {present && (
        <span
          className="rounded-pill bg-error-on-dark/20 px-2.5 py-0.5 text-sm text-error-on-dark"
          title="Both racers can see this. The agent takes it automatically."
        >
          on this page ◦
        </span>
      )}
    </div>
  );
}
export default TargetBadge;
