import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// 开发代理：把 /v1 REST 和 WebSocket 转发到后端 9000，避免跨域。
export default defineConfig({
  base: /app/,
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: "http://localhost:9000", changeOrigin: true, ws: true },
    },
  },
});
