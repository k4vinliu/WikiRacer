/**
 * CP0's artifact (FRONTEND.md §10): proves the toolchain, the fonts and the
 * frozen tokens all work together. Lane A replaces this with the real phase
 * switch (setup | arming | countdown | racing | finished) in task 10.
 *
 * Deliberately shows one of everything the design system has to get right:
 * the beige gradient page, a portrait card in card-green, lowercase Fraunces
 * left-aligned inside it (per the reference composition, §3.1), Inter muted
 * body copy, a grey pill and the single black CTA, and the digit slots that
 * work around Fraunces having no tabular figures (§3.3).
 */
export default function App() {
  return (
    <main className="min-h-screen p-6 font-body">
      <nav className="mx-auto flex max-w-5xl items-center justify-between px-2 py-2">
        <span className="font-medium text-text-on-light">Wikirace</span>
        <button
          type="button"
          className="rounded-pill bg-surface-grey px-4 py-2 text-sm font-medium text-text-on-light"
        >
          How it works
        </button>
      </nav>

      <div className="mt-16 flex justify-center">
        {/* Portrait hero card, content LEFT-aligned. The card is centred; its
            contents are not — see §3.1. */}
        <section className="on-dark flex w-[min(630px,92vw)] flex-col rounded-hero bg-card-green p-10 shadow-hero">
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight text-text-on-dark">
            wikirace
            <br />
            the agent
          </h1>

          <p className="mt-6 max-w-md text-lg leading-snug text-text-on-dark-muted">
            Race a web agent from one Wikipedia article to another. First to land
            on the target wins.
          </p>

          {/* The timer, in its fixed-width slots. 0.64em per digit, 0.28em for
              the colon — measured against the pinned-axis Fraunces file. */}
          <div className="mt-12 font-display tabular-slots text-[92px] leading-none text-text-on-dark">
            {[..."00:00"].map((c, i) => (
              <span
                key={i}
                style={{
                  display: "inline-block",
                  width: c === ":" ? "0.28em" : "0.64em",
                  textAlign: "center",
                }}
              >
                {c}
              </span>
            ))}
          </div>

          <div className="mt-auto pt-12">
            <p className="text-sm text-text-on-dark-muted">Where to where?</p>
            <button
              type="button"
              className="mt-3 rounded-pill bg-accent-black px-7 py-3.5 font-medium text-text-on-dark"
            >
              Start Race
            </button>
          </div>
        </section>
      </div>

      <p className="mx-auto mt-10 max-w-5xl px-2 text-center text-sm text-text-on-light-muted">
        CP0 scaffold — see <code>FRONTEND.md</code> §9 for your lane.
      </p>
    </main>
  );
}
