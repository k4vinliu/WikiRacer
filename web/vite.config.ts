// Tailwind v4 is a VITE PLUGIN. There is no tailwind.config.js, no postcss.config.js,
// and `npx tailwindcss init -p` does not exist. See FRONTEND.md §3.5.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
});
