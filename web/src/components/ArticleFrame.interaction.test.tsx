/**
 * The click gate, tested for real. Lane B.
 *
 * This file exists because of a bug that shipped: `onCandidates` was in the
 * effect's dependency array, callers pass inline arrows, so the effect re-ran on
 * every render, rewrote the document, and tore the click listener down as fast
 * as it was attached. Clicking a link did nothing — and NOTHING in the suite
 * noticed, because every other test exercises `extractCandidates` directly and
 * never mounts the component.
 *
 * So: mount it, click things, assert.
 */
import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ArticleFrame from "./ArticleFrame";

const HTML = `
  <div class="mw-parser-output">
    <p>
      <a id="legal" href="/wiki/Squamata">squamate</a>
      <a id="target" href="/wiki/Reptile">reptiles</a>
    </p>
    <div class="navbox"><a id="illegal" href="/wiki/Navbox_only">nav</a></div>
    <sup class="reference"><a id="cite" href="/wiki/Cited">[1]</a></sup>
  </div>`;

/** The frame is written with document.write, so wait for it to settle. */
async function mountFrame(props: Partial<React.ComponentProps<typeof ArticleFrame>> = {}) {
  const onMove = vi.fn();
  const onCandidates = vi.fn();
  const r = render(
    <ArticleFrame
      html={HTML}
      title="Snake"
      targetTitle="Reptile"
      onMove={onMove}
      onCandidates={onCandidates}
      {...props}
    />,
  );
  const frame = r.container.querySelector("iframe") as HTMLIFrameElement;
  await waitFor(() => expect(frame.contentDocument?.getElementById("legal")).toBeTruthy());
  return { frame, doc: frame.contentDocument!, onMove, onCandidates, r };
}

const click = (doc: Document, id: string) =>
  doc.getElementById(id)!.dispatchEvent(
    new doc.defaultView!.MouseEvent("click", { bubbles: true, cancelable: true }),
  );

describe("ArticleFrame click gate", () => {
  it("fires onMove for a legal link, with the anchor text", async () => {
    const { doc, onMove } = await mountFrame();
    click(doc, "legal");
    expect(onMove).toHaveBeenCalledWith({ title: "Squamata", anchorText: "squamate" });
  });

  it("does NOT fire for a link the extractor excluded", async () => {
    const { doc, onMove } = await mountFrame();
    click(doc, "illegal"); // inside .navbox
    click(doc, "cite");    // inside .reference
    expect(onMove).not.toHaveBeenCalled();
  });

  it("always preventDefaults, so a click can never navigate the frame", async () => {
    const { doc } = await mountFrame();
    for (const id of ["legal", "illegal", "cite"]) {
      const ev = new doc.defaultView!.MouseEvent("click", { bubbles: true, cancelable: true });
      doc.getElementById(id)!.dispatchEvent(ev);
      expect(ev.defaultPrevented).toBe(true);
    }
  });

  it("ignores clicks when not interactive (agent pane, finished race)", async () => {
    const { doc, onMove } = await mountFrame({ interactive: false });
    click(doc, "legal");
    expect(onMove).not.toHaveBeenCalled();
  });

  it("marks the target link and reports its presence", async () => {
    const { doc, onCandidates } = await mountFrame();
    expect(doc.getElementById("target")!.hasAttribute("data-wr-target")).toBe(true);
    expect(doc.getElementById("legal")!.hasAttribute("data-wr-target")).toBe(false);
    const [, targetPresent] = onCandidates.mock.calls.at(-1)!;
    expect(targetPresent).toBe(true);
  });

  it("reports targetPresent=false when the target is not on the page", async () => {
    const { onCandidates } = await mountFrame({ targetTitle: "Kangaroo" });
    const [, targetPresent] = onCandidates.mock.calls.at(-1)!;
    expect(targetPresent).toBe(false);
  });

  /* ---- THE REGRESSION ---- */
  it("does not rewrite the document on re-render (the effect-loop bug)", async () => {
    const { r, onCandidates } = await mountFrame();
    const afterMount = onCandidates.mock.calls.length;
    // Re-render with a NEW inline callback identity, exactly as a real caller
    // does on every state update.
    r.rerender(
      <ArticleFrame
        html={HTML}
        title="Snake"
        targetTitle="Reptile"
        onMove={() => {}}
        onCandidates={(n, t) => onCandidates(n, t)}
      />,
    );
    await new Promise((res) => setTimeout(res, 30));
    expect(onCandidates.mock.calls.length).toBe(afterMount);
  });

  it("still works after a re-render — the listener survives", async () => {
    const { doc, onMove, r } = await mountFrame();
    r.rerender(
      <ArticleFrame
        html={HTML}
        title="Snake"
        targetTitle="Reptile"
        onMove={onMove}
        onCandidates={() => {}}
      />,
    );
    click(doc, "legal");
    expect(onMove).toHaveBeenCalledTimes(1);
  });
});
