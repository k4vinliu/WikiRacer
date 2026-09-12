/** The only module that may talk to wikipedia.org. FRONTEND.md §5.1. */

import { normalizeTitle, sameArticle as titlesMatch } from "./links";

export { normalizeTitle, titlesMatch };

export class WikiError extends Error {
  status: number;
  constructor(status: number, message?: string) {
    super(message ?? `Wikipedia request failed (${status})`);
    this.name = "WikiError";
    this.status = status;
  }
}

const API = "https://en.wikipedia.org/w/api.php";
const FETCH_MS = 10_000;
const MAX_INFLIGHT = 3;

export const enc = (t: string) => encodeURIComponent(t.replace(/ /g, "_"));

export const parseUrl = (t: string) =>
  `${API}?action=parse&page=${enc(t)}&prop=text&redirects=1&disableeditsection=true` +
  `&format=json&formatversion=2&origin=*`;

export const canonUrl = (ts: string[]) =>
  `${API}?action=query&titles=${ts.map(enc).join("|")}&redirects=1` +
  `&format=json&formatversion=2&origin=*`;

export const searchUrl = (q: string) =>
  `${API}?action=opensearch&search=${encodeURIComponent(q)}&limit=8&namespace=0` +
  `&format=json&origin=*`;

export const key = (t: string) => String(t).replace(/ /g, "_");

export const resolve = (t: string, m: Map<string, string>) => {
  const x = m.get(key(t)) ?? m.get(t) ?? t;
  return m.get(x) ?? x;
};

type ParseJson = {
  parse?: { title?: string; text?: string };
  error?: { code?: string; info?: string };
};

type QueryPage = { title?: string; missing?: boolean | "" };
type QueryJson = {
  query?: {
    pages?: QueryPage[];
    normalized?: { from: string; to: string }[];
    redirects?: { from: string; to: string }[];
  };
  error?: { code?: string; info?: string };
};

export type Article = { title: string; html: string };

export type FieldError = { field: "start" | "target" | "both"; msg: string };
export type ValidateOk = { ok: true; start: string; target: string };
export type ValidateFail = { ok: false } & FieldError;
export type ValidateResult = ValidateOk | ValidateFail;

const articleCache = new Map<string, Article>();
let inflight = 0;
const waiters: (() => void)[] = [];

async function withSlot<T>(fn: () => Promise<T>): Promise<T> {
  if (inflight >= MAX_INFLIGHT) {
    await new Promise<void>((r) => {
      waiters.push(r);
    });
  }
  inflight += 1;
  try {
    return await fn();
  } finally {
    inflight -= 1;
    waiters.shift()?.();
  }
}

async function wikiFetch(url: string, attempt = 0): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_MS);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    if (res.status === 429 && attempt < 3) {
      await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
      return wikiFetch(url, attempt + 1);
    }
    if (!res.ok) throw new WikiError(res.status);
    return res;
  } catch (err) {
    if (err instanceof WikiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new WikiError(408, "Wikipedia timed out. Try again.");
    }
    throw new WikiError(0, "Could not reach Wikipedia.");
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchArticle(title: string): Promise<Article> {
  const hit = [...articleCache.values()].find((a) => titlesMatch(a.title, title));
  if (hit) return hit;

  return withSlot(async () => {
    const again = [...articleCache.values()].find((a) => titlesMatch(a.title, title));
    if (again) return again;

    const res = await wikiFetch(parseUrl(title));
    let data: ParseJson;
    try {
      data = (await res.json()) as ParseJson;
    } catch {
      throw new WikiError(res.status, "Wikipedia returned a non-JSON body.");
    }
    if (data.error?.code === "missingtitle") {
      throw new WikiError(404, "No such article.");
    }
    if (data.error || !data.parse?.title || data.parse.text == null) {
      throw new WikiError(502, data.error?.info ?? "Could not parse that article.");
    }
    const article: Article = { title: data.parse.title, html: data.parse.text };
    articleCache.set(normalizeTitle(article.title), article);
    return article;
  });
}

function chainMap(data: QueryJson): Map<string, string> {
  const m = new Map<string, string>();
  for (const n of data.query?.normalized ?? []) {
    m.set(n.from, n.to);
    m.set(key(n.from), n.to);
  }
  for (const r of data.query?.redirects ?? []) {
    m.set(r.from, r.to);
    m.set(key(r.from), r.to);
  }
  return m;
}

export async function validateTitles(start: string, target: string): Promise<ValidateResult> {
  const a = start.trim();
  const b = target.trim();
  if (!a || !b) {
    return { ok: false, field: !a ? "start" : "target", msg: "Enter an article title." };
  }

  return withSlot(async () => {
    const res = await wikiFetch(canonUrl([a, b]));
    let data: QueryJson;
    try {
      data = (await res.json()) as QueryJson;
    } catch {
      throw new WikiError(res.status, "Wikipedia returned a non-JSON body.");
    }
    if (data.error) {
      throw new WikiError(502, data.error.info ?? "Title lookup failed.");
    }

    const m = chainMap(data);
    const startCanon = resolve(a, m);
    const targetCanon = resolve(b, m);
    const pages = data.query?.pages ?? [];
    const isMissing = (p: QueryPage | undefined) =>
      !p || p.missing === true || p.missing === "";
    const pageFor = (title: string) =>
      pages.find((p) => titlesMatch(p.title ?? "", title)) ??
      pages.find((p) => titlesMatch(p.title ?? "", resolve(title, m)));

    const startPage = pageFor(startCanon);
    const targetPage = pageFor(targetCanon);
    const startGone = isMissing(startPage);
    const targetGone = isMissing(targetPage);
    if (startGone && targetGone) {
      return { ok: false, field: "both", msg: "No such article." };
    }
    if (startGone || !startPage) return { ok: false, field: "start", msg: "No such article." };
    if (targetGone || !targetPage) return { ok: false, field: "target", msg: "No such article." };

    const startTitle = startPage.title ?? startCanon;
    const targetTitle = targetPage.title ?? targetCanon;
    if (titlesMatch(startTitle, targetTitle)) {
      return { ok: false, field: "both", msg: "Pick two different articles." };
    }
    return { ok: true, start: startTitle, target: targetTitle };
  });
}

export async function searchTitles(q: string): Promise<string[]> {
  const query = q.trim();
  if (query.length < 1) return [];
  return withSlot(async () => {
    const res = await wikiFetch(searchUrl(query));
    const data = (await res.json()) as unknown;
    if (!Array.isArray(data) || !Array.isArray(data[1])) return [];
    return (data[1] as unknown[]).filter((t): t is string => typeof t === "string");
  });
}
