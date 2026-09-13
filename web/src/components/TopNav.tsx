import { useState } from "react";
import { Pill } from "./Pill";

export function HowItWorksDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-accent-black/40 p-6"
      onClick={onClose}
    >
      <div
        className="on-dark w-[min(480px,92vw)] rounded-card bg-card-green p-8 text-left text-text-on-dark shadow-hero"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="font-display text-3xl leading-tight">How it works</h2>
        <div className="mt-4 space-y-3 text-text-on-dark-muted leading-relaxed">
          <p>You and the agent start on the same Wikipedia article. First to the target wins.</p>
          <p>Move only by clicking article-body links. The clock is shared and starts after both of you are ready — not when you press Start.</p>
          <p>Win checks use the canonical title, so a redirect like “Obama” still counts as Barack Obama.</p>
          <p className="font-display-wonk text-text-on-dark">
            Keyboard hints stay here, off the race HUD.
          </p>
        </div>
        <div className="mt-6">
          <Pill variant="black" size="sm" onClick={onClose}>
            Close
          </Pill>
        </div>
      </div>
    </div>
  );
}

export function TopNav() {
  const [open, setOpen] = useState(false);
  return (
    <nav className="mx-auto flex max-w-5xl items-center justify-between px-2 py-2">
      <span className="font-medium text-text-on-light">Wikirace</span>
      <Pill variant="grey" size="sm" onClick={() => setOpen(true)}>
        How it works
      </Pill>
      <HowItWorksDialog open={open} onClose={() => setOpen(false)} />
    </nav>
  );
}
