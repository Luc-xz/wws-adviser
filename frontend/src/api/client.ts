import createClient from "openapi-fetch";

import type { paths } from "./generated/types";

const client = createClient<paths>({ baseUrl: "/" });

// 中间件：每次请求注入 X-Request-ID；写方法注入 X-CSRF-Token（double-submit）
client.use({
  async onRequest({ request }) {
    request.headers.set("X-Request-ID", crypto.randomUUID());
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
      const csrf = readCookie("csrf_token");
      if (csrf) request.headers.set("X-CSRF-Token", csrf);
    }
    return request;
  },
});

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

export default client;
