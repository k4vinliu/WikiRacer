/**
 * THE GAME RULE, in TypeScript. Lane B.
 *
 * `speedrun/links.py` is the other half of this file and the two MUST agree —
 * if the player and the agent have different move sets, one of them gets robbed
 * of a win. Any change here is a change there, in the same commit.
 * See FRONTEND.md §5.3 and PLAN.md §4.A.
 *
 * Pure. No fetch, no DOM construction, no React. Takes a parsed Document.
 */

import type { Pair } from "../agent/types";

/* ------------------------------------------------------------------ *
 * The exclusion list. This is ALSO the CSS hide list.
 *
 * These two mechanisms must have one source of truth. v1 of this spec kept
 * them separate and they drifted: measured visible-and-clickable-but-illegal
 * links were 157 on `Python (programming language)`, 68 on `Roman Empire`,
 * 20 on `Pizza`, 13 on `Cat`. On our own demo start page, 151 of those 157
 * were a single `.sidebar` block — and because MediaWiki's collapsing is
 * JS-driven and we load no JS, that sidebar renders FULLY EXPANDED.
 *
 * `article.css` imports EXCLUDE_SELECTOR. Do not hand-maintain a second list.
 * ------------------------------------------------------------------ */
export const EXCLUDE = [
  // navigation chrome
  ".navbox",
  ".navbox-styles",
  ".vertical-navbox",
  ".sidebar",
  ".side-box",
  ".sistersitebox",
  ".metadata",
  ".portalbox",
  ".navbar",
  ".catlinks",
  // collapsed / non-rendering
  ".mw-collapsed",
  ".noprint",
  "[hidden]",
  // citations. The frontend needs these and PLAN.md §4.A's list omitted them:
  // without them the player gets 67 extra titles on `Cat` and 218 on
  // `Roman Empire`, including race-winning hubs like `BBC News`.
  ".reference",
  ".reflist",
  ".mw-references-wrap",
  "ol.references",
  // editorial affordances
  ".mw-editsection",
  ".mw-jump-link",
] as const;

export const EXCLUDE_SELECTOR = EXCLUDE.join(", ");

/**
 * DELIBERATELY NOT EXCLUDED — both were checked, both are legal moves:
 *  - `.infobox`  — 69 legitimate links on the Python article.
 *  - `.hatnote`  — body content, frequently literal inline "See also:" lines,
 *                  i.e. exactly the lateral move that wins wiki races.
 * A grep gate in FRONTEND.md §10 fails the build if `hatnote` appears in
 * `src/styles/`. If you are about to hide one of these, read §5.3 first.
 */

/** Non-article namespaces. Matched against the segment before the first colon,
 *  NOT a "contains a colon" check — `Batman: The Animated Series` is a real
 *  article and must survive. */
const NAMESPACES = new Set([
  "File", "Image", "Media", "Category", "Special", "Help", "Portal",
  "Template", "Module", "Draft", "User", "Wikipedia", "Project",
  "MediaWiki", "TimedText", "Book", "Talk",
  "File talk", "Category talk", "Help talk", "Portal talk", "Template talk",
  "Module talk", "Draft talk", "User talk", "Wikipedia talk", "Project talk",
  "MediaWiki talk", "TimedText talk", "Book talk",
]);

/**
 * Accepts BOTH href forms, because we genuinely see both:
 *  - `action=parse&prop=text` (what the frontend fetches) emits `/wiki/Foo`
 *  - the read view (what `steel browser content` returns, and what our
 *    committed fixture is) emits `https://en.wikipedia.org/wiki/Foo`
 * A third form exists and we must never accept it: `rest_v1/page/html` emits
 * `./Foo`, and a `./`-relative href resolved against our own origin is not a
 * Wikipedia article. See FRONTEND.md §2.2.
 */
const ARTICLE_HREF = /^(?:https?:\/\/en\.wikipedia\.org)?\/wiki\/([^?#]+)(#.*)?$/;

export interface Candidate {
  index: number;
  text: string;
  title: string;
  href: string;
  isRedirect: boolean;
}

/** Wikipedia titles are case-sensitive except for the first character. */
const ucfirst = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export function normalizeTitle(raw: string): string {
  let t = raw;
  try {
    t = decodeURIComponent(t);
  } catch {
    /* a stray % that isn't an escape — use the raw string */
  }
  return ucfirst(t.replace(/_/g, " ").trim());
}

/** The only title comparison in the app. Both racers' wins run through it. */
export const sameArticle = (a: string, b: string) =>
  normalizeTitle(a) === normalizeTitle(b);

export const isWin = (current: string, target: string) =>
  sameArticle(current, target);

/** `/wiki/`-form title out of an href, or null if it isn't a legal article link. */
export function titleFromHref(href: string | null): string | null {
  if (!href) return null;
  const m = ARTICLE_HREF.exec(href.trim());
  if (!m) return null;

  // Reject a cross-host href that happens to contain /wiki/. Real article
  // bodies link to things like code.google.com/p/x/wiki/Y.
  if (/^https?:\/\//.test(href) && !/^https?:\/\/en\.wikipedia\.org\//.test(href)) {
    return null;
  }
  if (/#cite_note|#cite_ref/.test(href)) return null;

  const title = normalizeTitle(m[1]);
  if (!title) return null;
  const colon = title.indexOf(":");
  if (colon > 0 && NAMESPACES.has(title.slice(0, colon))) return null;
  return title;
}

/**
 * The legal move set for one article.
 *
 * @param doc       a Document or Element holding the article HTML. For
 *                  `action=parse` output this is the fragment; for the read
 *                  view it is the whole page and we scope to #mw-content-text.
 * @param selfTitle the article we are standing on — its self-links are not moves.
 *
 * Returns a Map so `ArticleFrame`'s click handler can gate on membership in
 * O(1). That gate is not optional: CSS `display:none` alone has already been
 * shown to leak 157 illegal links on one page.
 */
export function extractCandidates(
  doc: Document | Element,
  selfTitle?: string,
  maxCandidates = 1000,
): Map<string, Candidate> {
  const root =
    ("querySelector" in doc ? doc.querySelector("#mw-content-text") : null) ??
    ("querySelector" in doc ? doc.querySelector(".mw-parser-output") : null) ??
    doc;

  // Work on a clone: the caller's DOM is also what we render, and the CSS hide
  // list handles the visual side. Mutating here would fight that.
  const scratch = (root as Element).cloneNode(true) as Element;
  for (const node of Array.from(scratch.querySelectorAll(EXCLUDE_SELECTOR))) {
    node.remove();
  }

  const out = new Map<string, Candidate>();
  const self = selfTitle ? normalizeTitle(selfTitle) : null;

  for (const a of Array.from(scratch.querySelectorAll("a[href]"))) {
    if (out.size >= maxCandidates) break;

    const href = a.getAttribute("href");
    const title = titleFromHref(href);
    if (!title || title === self) continue;
    if (out.has(title)) continue; // dedupe by title, first occurrence wins

    // Red links point at articles that do not exist — not a legal move.
    if (a.classList.contains("new")) continue;

    const text = (a.textContent ?? "").trim();
    out.set(title, {
      index: out.size, // 0-BASED and contiguous. See PLAN.md §4.C.
      text: text || title,
      title,
      href: href!,
      isRedirect: a.classList.contains("mw-redirect"),
    });
  }
  return out;
}

/**
 * Is the target link on this page? If so it is a guaranteed win, and both
 * racers get it: the agent via `links.find_target` (PLAN.md §4.A), the player
 * via the highlight in `ArticleFrame`.
 *
 * Must run BEFORE any truncation — PLAN.md §4.A measured real directly-linked
 * targets sitting past index 900 on long articles.
 */
export function findTarget(
  candidates: Map<string, Candidate>,
  targetTitle: string,
): Candidate | null {
  const want = normalizeTitle(targetTitle);
  const direct = candidates.get(want);
  if (direct) return direct;
  for (const c of candidates.values()) {
    if (sameArticle(c.title, want)) return c;
  }
  return null;
}

/** Human-readable move count for the trail. Both racers use "hops". */
export const hopsOf = (path: string[]) => Math.max(0, path.length - 1);

/** Sanity-check a curated pair at dev time (FRONTEND.md §5.4). */
export const pairLabel = (p: Pair) =>
  `${p.start} → ${p.target} (${p.atLeast ? "≥" : ""}${p.hops} hops)`;
