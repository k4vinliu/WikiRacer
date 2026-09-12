// Tailwind v4 is a VITE PLUGIN. There is no tailwind.config.js, no postcss.config.js,
// and `npx tailwindcss init -p` does not exist. See FRONTEND.md §3.5.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // the committed fixtures live above web/ — Lane B's preview page reads one
    fs: { allow: [".."] },
  },
  // article-preview.html is deliberately NOT a build input: Vite serves any
  // root-level .html in dev, and bundling it would ship a 582 KB fixture to
  // production. Lane B, dev-only.
});
