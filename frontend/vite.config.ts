import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base only changes for a production build -- local `npm run dev` still
// serves from / exactly as the README documents. The VM deploy (served
// under /gaf/ alongside the telecom-assistant app on the same domain)
// needs asset paths rewritten to /gaf/; a standalone host with its own
// domain (Vercel, Netlify, ...) needs plain / instead -- set the
// VITE_BASE_PATH env var at build time to override the default without
// touching this file (unset = unchanged /gaf/ behaviour for the VM).
export default defineConfig(({ command }) => ({
  base: command === "build" ? process.env.VITE_BASE_PATH || "/gaf/" : "/",
  plugins: [react()],
  server: {
    port: 5173,
  },
}));
