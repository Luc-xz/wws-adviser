import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import UnoCSS from "unocss/vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    vue(),
    UnoCSS(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "WWS Adviser",
        short_name: "WWS",
        description: "个人投资顾问",
        theme_color: "#3157D5",
        background_color: "#F5F7FA",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        runtimeCaching: [
          {
            // hashed 静态资源：Cache First
            urlPattern: /\.(?:js|css|svg|png|woff2?)$/,
            handler: "CacheFirst",
            options: { cacheName: "assets" },
          },
          {
            // intraday/行情/建议：Network Only（实时数据不缓存）
            urlPattern: /\/api\/v1\/(?:market-data|assistant|advice)/,
            handler: "NetworkOnly",
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
