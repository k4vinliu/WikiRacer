/** Lane B. The click gate is the important one. FRONTEND.md §5.2. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { extractCandidates, titleFromHref } from "../lib/links";

const parseFixture = () => {
  const p = resolve(__dirname, "../../../tests/fixtures/snake_parse.json");
  return JSON.parse(readFileSync(p, "utf-8")).parse as {
    title: string;
    text: string;
  };
};

describe("the action=parse flavour", () => {
  it("is a fragment with /wiki/ hrefs the extractor accepts", () => {
    const { title, text } = parseFixture();
    expect(title).toBe("Snake");
    expect(text).not.toContain('href="./');           // not rest_v1
    expect(text).not.toContain("mw-content-text");    // fragment, no wrapper
    const doc = new DOMParser().parseFromString(text, "text/html");
    const c = extractCandidates(doc, title);
    expect(c.size).toBeGreaterThan(200);
    expect(c.has("Snake")).toBe(false);               // self-link dropped
  });

  it("accepts the relative form and rejects rest_v1's", () => {
    expect(titleFromHref("/wiki/Reptile")).toBe("Reptile");
    expect(titleFromHref("./Reptile")).toBeNull();
  });
});
