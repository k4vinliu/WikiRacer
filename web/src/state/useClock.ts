import { useEffect, useState } from "react";

/** The ONLY clock. Monotonic. rAF repaints; it does not measure. FRONTEND.md §2.6. */
export const elapsedMs = (t0: number) => performance.now() - t0;

export function useClock(t0: number | null, running: boolean, frozenMs: number | null): number {
  const [ms, setMs] = useState(0);

  useEffect(() => {
    if (t0 == null || !running) return;
    let raf = 0;
    const tick = () => {
      setMs(elapsedMs(t0));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [t0, running]);

  if (frozenMs != null) return frozenMs;
  if (t0 == null) return 0;
  return running ? ms : 0;
}
