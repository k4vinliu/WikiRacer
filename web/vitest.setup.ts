/**
 * Shared test setup. Loaded by vitest.config.ts for every test file.
 *
 * Two things, both of which cost real debugging time once:
 *
 * 1. jsdom implements no layout, so it ships NO `Element.prototype.scrollIntoView`
 *    -- calling it throws `TypeError: ... is not a function`. Any test that mounts
 *    a component which auto-scrolls (AgentLog pins the reasoning log to its newest
 *    row; Race and App render it) dies inside a passive effect, with a stack that
 *    points at React internals rather than the missing API. The stub is a no-op on
 *    purpose: asserting scroll position in jsdom would assert on a layout engine
 *    that isn't there.
 *
 * 2. We run with `globals: false`, so @testing-library/react cannot register its
 *    own `afterEach(cleanup)` -- that auto-registration only happens when the
 *    global `afterEach` exists. Without this, every `render()` leaves its tree
 *    mounted in `document.body` and the NEXT test queries a DOM containing both.
 *    That failure looks like a component bug ("the iframe is still there when
 *    liveUrl is null") and is not one.
 */
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}

afterEach(() => {
  cleanup();
});
