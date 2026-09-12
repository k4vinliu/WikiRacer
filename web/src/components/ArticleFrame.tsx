/**
 * The article well. Lane B. FRONTEND.md §5.2.
 *
 * Renders Wikipedia HTML into a SAME-ORIGIN srcdoc iframe. Read §2.1 before
 * changing the approach, because both halves of that decision are load-bearing:
 *
 *  - It is NOT a cross-origin frame pointed at wikipedia.org. Framing Wikipedia
 *    is allowed (no x-frame-options, no frame-ancestors) but a cross-origin
 *    frame is opaque: `contentDocument` returns null SILENTLY, so we could
 *    never know which article the player is on. No location ⇒ no win check ⇒
 *    no game.
 *  - It IS an iframe rather than a div, for CSS isolation. Wikipedia's content
 *    stylesheet has unscoped `a { color:#0645ad }`; inlining article.css into
 *    the app document would repaint the whole UI. Shadow DOM does not work
 *    either — the payload carries ~19 inline TemplateStyles blocks whose
 *    selectors are prefixed `body.skin-vector-2022`, and a shadow root has no
 *    `body` ancestor, so infoboxes and reflists silently break.
 *
 * Interaction: ONE delegated click listener on the frame's body, gated on the
 * candidate Map. The gate is not optional — CSS `display:none` alone has been
 * measured leaking 157 clickable-but-illegal links on one page.
 */

import { useEffect, useLayoutEffect, useRef } from "react";

import articleCss from "../styles/article.css?raw";
import {
  EXCLUDE_SELECTOR,
  extractCandidates,
  normalizeTitle,
  titleFromHref,
  type Candidate,
} from "../lib/links";

export interface ArticleMove {
  title: string;
  /** The anchor text as it appeared on the page. Carries PLAN.md §4.D's
   *  obligation for the human side, symmetrically with the agent's. */
  anchorText: string;
}

export interface ArticleFrameProps {
  /** Raw `action=parse&prop=text` HTML fragment. */
  html: string;
  /** Canonical title of the article being shown (from `parse.title`). */
  title: string;
  /** Canonical target, so the winning link can be highlighted. */
  targetTitle?: string;
  /** False for the agent's pane and after the race ends: renders identically,
   *  ignores clicks. */
  interactive?: boolean;
  /** Fires only for LEGAL moves. */
  onMove?: (move: ArticleMove) => void;
  /** Legal-move count, for the panel header. */
  onCandidates?: (n: number, targetPresent: boolean) => void;
  className?: string;
}

/** Wikipedia emits protocol-relative image URLs (`src="//upload..."`). Verified:
 *  all 48 images on the `Snake` fixture. Inside a document.write'n frame on
 *  `http://localhost:5173` each one resolves to http:// and eats a redirect, so
 *  pin them to https. */
const pinProtocol = (html: string) =>
  html.replace(/(\s(?:src|srcset|href)=")\/\//g, '$1https://');

export function ArticleFrame({
  html,
  title,
  targetTitle,
  interactive = true,
  onMove,
  onCandidates,
  className,
}: ArticleFrameProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  // Keep the live callbacks and candidate set in refs: the click listener is
  // attached once per document write, and must never close over a stale prop.
  const onMoveRef = useRef(onMove);
  const candidatesRef = useRef<Map<string, Candidate>>(new Map());
  const interactiveRef = useRef(interactive);

  useLayoutEffect(() => {
    onMoveRef.current = onMove;
    interactiveRef.current = interactive;
  }, [onMove, interactive]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    const doc = frame.contentDocument;
    if (!doc) return; // same-origin, so this is only null pre-mount

    // The hide list is GENERATED from the extractor's exclusion list, so the
    // two can never drift. Do not hand-write a selector list here.
    const hideRule = `${EXCLUDE_SELECTOR} { display: none !important; }`;

    doc.open();
    doc.write(
      `<!doctype html><html><head><meta charset="utf-8">` +
        `<base target="_self">` +
        `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>` +
        `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400..600&family=Inter:wght@400;500;600&display=swap">` +
        // Inlined, not <link>ed: a stylesheet request inside a freshly written
        // document makes hop 1 flash unstyled at exactly the moment the race
        // starts.
        `<style>${articleCss}</style><style>${hideRule}</style>` +
        `</head><body>${pinProtocol(html)}</body></html>`,
    );
    doc.close();

    // Extract AFTER the hide list is in the document but from the real DOM, so
    // the extractor sees exactly what the player sees.
    const candidates = extractCandidates(doc, title);
    candidatesRef.current = candidates;

    // Mark the winning link, if it is on this page. FRONTEND.md decision 4.
    let targetPresent = false;
    if (targetTitle) {
      const want = normalizeTitle(targetTitle);
      for (const a of Array.from(doc.querySelectorAll("a[href]"))) {
        const t = titleFromHref(a.getAttribute("href"));
        if (t && t === want && candidates.has(t)) {
          a.setAttribute("data-wr-target", "");
          targetPresent = true;
        }
      }
    }
    onCandidates?.(candidates.size, targetPresent);

    const onClick = (e: MouseEvent) => {
      const el = e.target as Element | null;
      const a = el?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!a) return;

      // preventDefault ALWAYS, legal or not. A stray navigation inside the
      // frame would leave the player on a page we are not tracking, and the
      // parent would have no idea.
      e.preventDefault();
      if (!interactiveRef.current) return;

      const t = titleFromHref(a.getAttribute("href"));
      // THE GATE. Anything not in the candidate set is not a legal move,
      // regardless of what CSS did or did not hide.
      if (!t || !candidatesRef.current.has(t)) {
        a.setAttribute("data-wr-illegal", "");
        return;
      }
      onMoveRef.current?.({
        title: t,
        anchorText: (a.textContent ?? "").trim() || t,
      });
    };

    doc.body.addEventListener("click", onClick);
    // Middle-click and ctrl-click would open a real tab out of our app.
    const onAux = (e: MouseEvent) => e.preventDefault();
    doc.body.addEventListener("auxclick", onAux);
    // Suppress the frame's own context menu: "Open link in new tab" is an exit.
    const onMenu = (e: Event) => e.preventDefault();
    doc.body.addEventListener("contextmenu", onMenu);

    return () => {
      doc.body.removeEventListener("click", onClick);
      doc.body.removeEventListener("auxclick", onAux);
      doc.body.removeEventListener("contextmenu", onMenu);
    };
  }, [html, title, targetTitle, onCandidates]);

  return (
    <iframe
      ref={frameRef}
      title={`Article: ${title}`}
      className={className}
      // No allow-popups, no allow-top-navigation. allow-same-origin is required
      // — the whole design depends on reading contentDocument.
      sandbox="allow-same-origin"
      style={{ width: "100%", height: "100%", border: 0, display: "block" }}
    />
  );
}

export default ArticleFrame;
