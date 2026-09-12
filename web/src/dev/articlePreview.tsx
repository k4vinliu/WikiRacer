/**
 * CP1's gate, standalone. Lane B.
 *
 * Answers the one question that could force a design rethink: does 580 KB of
 * `mw-parser-output` look good inside a sage-green card on a warm well?
 * FRONTEND.md §10 wants that answered at hour two, not hour eight.
 *
 *     npm --prefix web run dev   ->  http://localhost:5173/article-preview.html
 *
 * Fully offline: renders the committed `action=parse` fixture. Does NOT touch
 * App.tsx or anything Lane A owns. Delete once Race.tsx is real.
 */
import { useState } from "react";
import { createRoot } from "react-dom/client";

import ArticleFrame, { type ArticleMove } from "../components/ArticleFrame";
import "../styles/theme.css";
import fixture from "../../../tests/fixtures/snake_parse.json";

const { title, text } = (fixture as { parse: { title: string; text: string } }).parse;

function Preview() {
  const [moves, setMoves] = useState<ArticleMove[]>([]);
  const [stats, setStats] = useState({ n: 0, target: false });
  // "Reptile" is a real body link on Snake, so the highlight is exercised.
  const target = "Reptile";

  return (
    <main className="min-h-screen p-5 font-body">
      <div className="mx-auto flex max-w-[1920px] gap-4">
        {/* Exactly the Race screen's player panel: 896px card, 16:9-ish well. */}
        <section className="on-dark flex w-[896px] shrink-0 flex-col rounded-card bg-card-green p-4 shadow-card">
          <header className="flex items-baseline justify-between px-1 pb-3">
            <h2 className="font-medium text-text-on-dark">
              YOU · {title}
              <span className="ml-2 text-text-on-dark-muted">
                {stats.n} legal links
              </span>
            </h2>
            <span className="text-sm text-text-on-dark-muted">
              {stats.target ? "target is on this page ◦" : `reach: ${target}`}
            </span>
          </header>
          <div className="h-[820px] overflow-hidden rounded-[18px] bg-surface-well">
            <ArticleFrame
              html={text}
              title={title}
              targetTitle={target}
              onMove={(m) => setMoves((p) => [...p, m])}
              onCandidates={(n, t) => setStats({ n, target: t })}
            />
          </div>
        </section>

        <aside className="flex-1 rounded-card bg-surface-grey p-5 shadow-card">
          <h3 className="font-display text-2xl">click trail</h3>
          <p className="mt-1 text-sm text-text-on-light-muted">
            Only legal moves appear here. Try a reference marker, a navbox link
            or the search box — nothing should fire.
          </p>
          <ol className="mt-4 space-y-1 text-sm">
            {moves.map((m, i) => (
              <li key={i}>
                <span className="text-text-on-light-muted">{i + 1}.</span>{" "}
                <strong>{m.anchorText}</strong>{" "}
                <span className="text-text-on-light-muted">→ {m.title}</span>
              </li>
            ))}
            {!moves.length && (
              <li className="text-text-on-light-subtle">no clicks yet</li>
            )}
          </ol>
        </aside>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<Preview />);
