/**
 * Lane B. The TypeScript half of the game rule, plus — the important one — a
 * PARITY test against the Python half.
 *
 * FRONTEND.md §5.3: "One rule, two languages. If the player and the agent have
 * different move sets, one of them gets robbed of a win." Nothing in the
 * original spec actually *checked* that, so this file does. The parity fixture
 * is regenerated with:
 *
 *     python3.11 -c "from speedrun.links import extract_candidates; import json; \
 *       json.dump([c.title for c in extract_candidates(open( \
 *       'tests/fixtures/python_programming_language.html',encoding='utf-8').read())], \
 *       open('web/src/lib/__fixtures__/py_titles.json','w'))"
 *
 * Run: npm --prefix web run test
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

import { titlesMatch } from "./wikiApi";
import pyTitleParity from "./__fixtures__/py_title_parity.json";
import {
  EXCLUDE_SELECTOR,
  extractCandidates,
  findTarget,
  isWin,
  normalizeTitle,
  sameArticle,
  titleFromHref,
} from "./links";

const W = "https://en.wikipedia.org/wiki";
const parse = (body: string) =>
  new DOMParser().parseFromString(
    `<html><body><div id="mw-content-text">${body}</div></body></html>`,
    "text/html",
  );
const titles = (body: string, self?: string) =>
  [...extractCandidates(parse(body), self).values()].map((c) => c.title);

/* ------------------------------------------------------------------ *
 * The real page. Same assertion as tests/test_links.py, same fixture.
 * ------------------------------------------------------------------ */
describe("against the real committed article", () => {
  let doc: Document;
  let pyTitles: string[];

  beforeAll(() => {
    const root = resolve(__dirname, "../../..");
    doc = new DOMParser().parseFromString(
      readFileSync(
        resolve(root, "tests/fixtures/python_programming_language.html"),
        "utf-8",
      ),
      "text/html",
    );
    pyTitles = JSON.parse(
      readFileSync(resolve(__dirname, "__fixtures__/py_titles.json"), "utf-8"),
    );
  });

  it("yields many candidates — the v1-killer", () => {
    // Wikipedia serves ABSOLUTE hrefs in article bodies. If this is 0, the href
    // filter is rejecting them. FRONTEND.md §2.2.
    expect(extractCandidates(doc).size).toBeGreaterThan(200);
  });

  it("contains a known body link", () => {
    expect(extractCandidates(doc).has("Guido van Rossum")).toBe(true);
  });

  it("emits 0-based contiguous indices", () => {
    const idx = [...extractCandidates(doc).values()].map((c) => c.index);
    expect(idx).toEqual(idx.map((_, i) => i));
  });

  it("strips navigation chrome", () => {
    expect(extractCandidates(doc).has("Comparison of programming languages"))
      .toBe(false);
  });

  /* ---- THE PARITY TEST ---- */
  it("agrees with speedrun/links.py exactly, in the same order", () => {
    const ts = [...extractCandidates(doc).values()].map((c) => c.title);
    const onlyTs = ts.filter((t) => !pyTitles.includes(t));
    const onlyPy = pyTitles.filter((t) => !ts.includes(t));
    // Report the diff rather than just a count — a bare length mismatch tells
    // you nothing about WHICH rule drifted.
    expect({ onlyTs, onlyPy }).toEqual({ onlyTs: [], onlyPy: [] });
    expect(ts).toEqual(pyTitles);
  });
});

/* ------------------------------------------------------------------ *
 * The rule. Hrefs written ABSOLUTE — an inline fixture using "/wiki/Foo"
 * agrees with a bug instead of catching it.
 * ------------------------------------------------------------------ */
describe("href acceptance", () => {
  it("takes absolute and root-relative, rejects cross-host and dupes", () => {
    expect(
      titles(`
        <a href="${W}/Renaissance">Renaissance</a>
        <a href="/wiki/Florence">Florence</a>
        <a href="https://code.google.com/p/x/wiki/Y">nope</a>
        <a href="${W}/Renaissance">dupe</a>`),
    ).toEqual(["Renaissance", "Florence"]);
  });

  it("rejects rest_v1's ./Title form", () => {
    // Resolving `./Foo` against OUR origin is not a Wikipedia article.
    expect(titleFromHref("./Renaissance")).toBeNull();
    expect(titles('<a href="./Renaissance">R</a>')).toEqual([]);
  });

  it("rejects namespaces but keeps colons in real titles", () => {
    expect(
      titles(`
        <a href="${W}/File:X.jpg">f</a>
        <a href="${W}/Category:Y">c</a>
        <a href="${W}/Special:Random">r</a>
        <a href="${W}/Batman:_The_Animated_Series">b</a>`),
    ).toEqual(["Batman: The Animated Series"]);
  });

  it("skips cite anchors and self-links", () => {
    expect(
      titles(
        `<a href="${W}/Snake#cite_note-1">c</a>
         <a href="${W}/Snake">self</a>
         <a href="${W}/Python_(genus)">o</a>`,
        "Snake",
      ),
    ).toEqual(["Python (genus)"]);
  });
});

describe("the exclusion list", () => {
  it("strips references, sidebars, navboxes, collapsed and noprint", () => {
    expect(
      titles(`
        <p><a href="${W}/Legal_one">1</a></p>
        <sup class="reference"><a href="${W}/Cite_link">[1]</a></sup>
        <div class="reflist"><a href="${W}/Reflist_link">r</a></div>
        <div class="sidebar"><a href="${W}/Sidebar_link">s</a></div>
        <div class="navbox"><a href="${W}/Navbox_link">n</a></div>
        <div class="mw-collapsed"><a href="${W}/Collapsed_link">c</a></div>
        <div class="noprint"><a href="${W}/Noprint_link">p</a></div>
        <p><a href="${W}/Legal_two">2</a></p>`),
    ).toEqual(["Legal one", "Legal two"]);
  });

  it("KEEPS infobox and hatnote links — both are legal moves", () => {
    expect(
      new Set(
        titles(`
          <div class="hatnote"><a href="${W}/Hatnote_target">see also</a></div>
          <table class="infobox"><tr><td>
            <a href="${W}/Infobox_target">box</a></td></tr></table>`),
      ),
    ).toEqual(new Set(["Hatnote target", "Infobox target"]));
  });

  it("is the same list article.css hides — one source of truth", () => {
    // §5.2: v1 kept the CSS hide list and the exclusion list separate and they
    // drifted, leaking 157 clickable-but-illegal links on one page.
    expect(EXCLUDE_SELECTOR).toContain(".sidebar");
    expect(EXCLUDE_SELECTOR).toContain(".reference");
    expect(EXCLUDE_SELECTOR).not.toContain("hatnote");
    expect(EXCLUDE_SELECTOR).not.toContain("infobox");
  });
});

describe("candidate shape", () => {
  it("flags redirects", () => {
    const [c] = [
      ...extractCandidates(
        parse(`<a class="mw-redirect" href="${W}/Serpentes">S</a>`),
      ).values(),
    ];
    expect(c.isRedirect).toBe(true);
  });

  it("skips red links", () => {
    expect(titles(`<a class="new" href="${W}/Nope">red</a>`)).toEqual([]);
  });

  it("falls back to the title when the anchor has no text", () => {
    const [c] = [
      ...extractCandidates(
        parse(`<a href="${W}/Renaissance"><img src="x.png"></a>`),
      ).values(),
    ];
    expect(c.text).toBe("Renaissance");
  });

  it("truncates and reindexes", () => {
    const many = Array.from(
      { length: 50 },
      (_, i) => `<a href="${W}/Article_${i}">a${i}</a>`,
    ).join("");
    const got = [...extractCandidates(parse(many), undefined, 10).values()];
    expect(got).toHaveLength(10);
    expect(got.map((c) => c.index)).toEqual([...Array(10).keys()]);
    expect(got[0].title).toBe("Article 0");
  });
});

describe("titles and wins", () => {
  it("normalizes underscores, entities and first-letter case", () => {
    expect(normalizeTitle("guido_van_Rossum")).toBe("Guido van Rossum");
    expect(normalizeTitle("Monty_Python%27s_Flying_Circus")).toBe(
      "Monty Python's Flying Circus",
    );
    expect(normalizeTitle("AT%26T")).toBe("AT&T");
    expect(normalizeTitle("Caf%C3%A9")).toBe("Café");
  });

  it("survives a stray percent that isn't an escape", () => {
    expect(() => normalizeTitle("100%_pure")).not.toThrow();
  });

  it("matches only genuinely equal articles", () => {
    expect(sameArticle("snake", "Snake")).toBe(true);
    expect(sameArticle("Guido_van_Rossum", "Guido van Rossum")).toBe(true);
    expect(sameArticle("Snake", "Snakes")).toBe(false);
    expect(isWin("Barack Obama", "Barack Obama")).toBe(true);
  });

  it("findTarget locates the winning link", () => {
    const c = extractCandidates(
      parse(`<a href="${W}/Kangaroo">roo</a><a href="${W}/Snake">s</a>`),
    );
    expect(findTarget(c, "kangaroo")?.title).toBe("Kangaroo");
    expect(findTarget(c, "Jupiter")).toBeNull();
  });
});

/* ------------------------------------------------------------------ *
 * CROSS-LANE CONTRACT. FRONTEND.md §2.6: "if the two are canonicalized
 * differently, one racer can be robbed of a win."
 *
 * Three implementations of one concept exist today — links.ts (here),
 * wikiApi.ts (Lane A, and it is the one gameStore uses to adjudicate the
 * HUMAN's win) and speedrun/wiki.py (the one race.py uses for the AGENT's).
 * This test fails the moment any of them drifts.
 * ------------------------------------------------------------------ */
describe("cross-lane title agreement", () => {
  const CASES: [string, string][] = [
    ["Snake", "Snake"],
    ["Snake", "snake"],
    ["Guido_van_Rossum", "Guido van Rossum"],
    ["Barack Obama", "barack obama"],
    ["AIDS", "Aids"],
    ["Python (programming language)", "python (PROGRAMMING language)"],
    ["A  double  space", "A double space"],
    ["  Snake  ", "Snake"],
    ["Caf%C3%A9", "Café"],
    ["Snake", "Snakes"],
    ["Monty_Python%27s_Flying_Circus", "Monty Python's Flying Circus"],
  ];

  it("agrees with wikiApi.titlesMatch on every case", () => {
    const disagree = CASES.filter(([a, b]) => sameArticle(a, b) !== titlesMatch(a, b))
      .map(([a, b]) => `${a} | ${b}`);
    expect(disagree).toEqual([]);
  });

  it("agrees with speedrun/wiki.py titles_match on every case", () => {
    // Generated by: python3.11 -c "from speedrun.wiki import titles_match; ..."
    // Regenerate with tests/gen_title_parity.py if these cases change.
    const py: Record<string, boolean> = pyTitleParity;
    const disagree = CASES.filter(
      ([a, b]) => sameArticle(a, b) !== py[`${a}\u0000${b}`],
    ).map(([a, b]) => `${a} | ${b}`);
    expect(disagree).toEqual([]);
  });

  it("keeps DISPLAY case while comparing case-insensitively", () => {
    // The candidate Map is keyed by display form, so the click gate and the
    // rendered anchor agree; comparison is a separate, looser question.
    expect(normalizeTitle("guido_van_Rossum")).toBe("Guido van Rossum");
    expect(normalizeTitle("A  double  space")).toBe("A double space");
    expect(sameArticle("A  double  space", "A double space")).toBe(true);
  });
});
