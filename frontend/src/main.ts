import { createApp } from "vue";
import { createPinia } from "pinia";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import "virtual:uno.css";
import App from "./App.vue";
import router from "./router";
import "./styles/global.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
// 服务端状态唯一入口（doc7 §2）：敏感接口经 SW NetworkOnly，不做离线缓存
app.use(VueQueryPlugin, {
  queryClient: new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  }),
});
app.mount("#app");
