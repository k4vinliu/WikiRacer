/** The agent's reasoning, live. Lane B.
 *
 *  This is what makes the agent legible to an audience, and it is also the one
 *  pane with motion while the live view shows a static page during an LLM call
 *  (FRONTEND.md §2.5). Newest LAST, capped, because a projector reads the
 *  bottom of a list fine and rich's ellipsis bug taught us not to crop the new
 *  rows (§3.3 sibling problem).
 */
import { useEffect, useRef } from "react";
import type { AgentEvent } from "../agent/types";

const fmt = (ms: number) =>
  `${Math.floor(ms / 1000)}.${Math.floor((ms % 1000) / 100)}s`;

export function AgentLog({
  events,
  status,
  message,
}: {
  events: AgentEvent[];
  status: string;
  message?: string | null;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const rows = events.filter((e) => e.t === "pick" || e.t === "done" || e.t === "error");

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [rows.length]);

  const thinking = events.filter((e) => e.t === "thinking").at(-1);

  return (
    <div className="flex h-full flex-col">
      <h3 className="px-1 pb-2 text-base uppercase tracking-wider text-text-on-dark-muted">
        agent reasoning
      </h3>
      <ol className="min-h-0 flex-1 space-y-2 overflow-y-auto px-1 text-base">
        {rows.map((e, i) => {
          if (e.t === "pick") {
            return (
              <li key={e.seq} className="flex gap-2">
                <span className="w-6 shrink-0 text-right text-text-on-dark-muted">
                  {i + 1}
                </span>
                <span className="w-12 shrink-0 text-text-on-dark-muted">
                  {fmt(e.at)}
                </span>
                <span className="min-w-0">
                  <span className="text-text-on-dark">
                    {e.from} → <strong>&ldquo;{e.anchor_text}&rdquo;</strong>
                  </span>
                  <span className="text-text-on-dark-muted">
                    {" "}
                    {e.was_fallback ? "[fallback] " : ""}
                    {e.reason}
                  </span>
                </span>
              </li>
            );
          }
          if (e.t === "done") {
            return (
              <li key={e.seq} className="pt-1 text-text-on-dark-muted">
                — {e.reason.replace(/_/g, " ")} after {e.hops} hops
                {e.message ? `: ${e.message}` : ""}
              </li>
            );
          }
          return (
            <li key={e.seq} className="text-error-on-dark">
              — {e.message}
            </li>
          );
        })}
        {status === "thinking" && thinking?.t === "thinking" && (
          <li className="flex gap-2 text-text-on-dark-muted">
            <span className="w-6 text-right">◔</span>
            <span>
              reading {thinking.article} · {thinking.n_candidates} legal links
            </span>
          </li>
        )}
        {status === "gave_up" && (
          <li className="pt-1 text-text-on-dark-muted">
            {message ?? "The agent gave up. Your race is still running."}
          </li>
        )}
        {!rows.length && status === "idle" && (
          <li className="text-text-on-dark-muted">waiting for the agent…</li>
        )}
        <div ref={endRef} />
      </ol>
    </div>
  );
}
export default AgentLog;
