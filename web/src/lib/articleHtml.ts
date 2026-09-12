/**
 * Fetch an article and turn it into a rendered document plus a legal move set.
 * Lane B. FRONTEND.md §5.1 / §5.3.
 *
 * The split with Lane A's `wikiApi.ts` is deliberate and worth keeping:
 *   wikiApi.ts  — owns the network. URLs, res.ok, the cache, the concurrency
 *                 cap, `WikiError`. It is the ONLY module that talks to
 *                 wikipedia.org.
 *   articleHtml — owns the interpretation. DOMParser, then the game rule.
 *
 * So this module has no fetch of its own and no URL strings.
 */

import { fetchArticle, type Article, WikiError } from "./wikiApi";
import { extractCandidates, findTarget, type Candidate } from "./links";

export interface LoadedArticle {
  /** Canonical title, straight from `parse.title` — already redirect-resolved
   *  by Wikipedia, which is why the frontend needs no separate canonical step.
   *  FRONTEND.md §2.2. */
  title: string;
  /** Raw fragment, handed to `ArticleFrame` untouched. */
  html: string;
  /** The legal move set, keyed by title for the O(1) click gate. */
  candidates: Map<string, Candidate>;
  /** The winning link, if it happens to be on this page. */
  target: Candidate | null;
}

/** Parse once, here, rather than per-component. jsdom and the browser both
 *  supply DOMParser, so this is testable without a React render. */
export function interpret(
  article: Article,
  targetTitle?: string,
): LoadedArticle {
  const doc = new DOMParser().parseFromString(article.html, "text/html");
  const candidates = extractCandidates(doc, article.title);
  return {
    title: article.title,
    html: article.html,
    candidates,
    target: targetTitle ? findTarget(candidates, targetTitle) : null,
  };
}

/**
 * Load an article and interpret it in one step.
 *
 * Errors are NOT swallowed: a `WikiError` propagates so the caller can show the
 * host something actionable. FRONTEND.md §5.1 — an unchecked Wikipedia 429
 * whose body flows into a parser yields an empty move set and a race that
 * silently cannot be won, which has already happened twice on this project.
 */
export async function loadArticle(
  title: string,
  targetTitle?: string,
): Promise<LoadedArticle> {
  return interpret(await fetchArticle(title), targetTitle);
}

/** A host-readable one-liner. Never show a stack trace on a projector. */
export function describeLoadError(err: unknown): string {
  if (err instanceof WikiError) {
    if (err.status === 404) return "No such article.";
    if (err.status === 429) return "Wikipedia is rate-limiting us — retrying.";
    return `Wikipedia error ${err.status}. ${err.message}`;
  }
  return err instanceof Error ? err.message : "Could not load that article.";
}
