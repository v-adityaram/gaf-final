import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base only changes for a production build -- local `npm run dev` still
// serves from / exactly as the README documents; only the VM deploy (served
// under /gaf/ alongside the telecom-assistant app on the same domain) needs
// asset paths rewritten.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/gaf/" : "/",
  plugins: [react()],
  server: {
    port: 5173,
  },
}));
