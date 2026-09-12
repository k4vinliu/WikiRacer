import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",   // links.ts takes a Document; jsdom supplies DOMParser
    globals: false,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
