// Web Push 订阅管理（Phase 3.5 P1）：权限 → 订阅 → 登记后端。
// VAPID 未配置（configured=false）时入口隐藏；权限拒绝静默降级。
import { ref } from "vue";
import client from "@/api/client";

export function urlBase64ToUint8Array(base64: string): ArrayBuffer {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes.buffer as ArrayBuffer;
}

export function usePushManager() {
  const supported = ref(
    typeof window !== "undefined" &&
      "serviceWorker" in navigator &&
      "PushManager" in window &&
      "Notification" in window,
  );
  const state = ref<"idle" | "enabling" | "enabled" | "denied" | "unsupported">("idle");

  async function enable(): Promise<void> {
    if (!supported.value) {
      state.value = "unsupported";
      return;
    }
    state.value = "enabling";
    try {
      const { data: cfg } = await client.GET("/api/v1/push/vapid-public");
      const vapidKey = cfg?.public_key;
      if (!cfg?.configured || typeof vapidKey !== "string") {
        state.value = "unsupported";
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        state.value = "denied";
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      const sub =
        (await reg.pushManager.getSubscription()) ??
        (await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidKey),
        }));
      const json = sub.toJSON();
      const keys = (json.keys ?? {}) as Record<string, string>;
      const { error } = await client.POST("/api/v1/push/subscriptions", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: { endpoint: json.endpoint ?? "", p256dh: keys.p256dh ?? "", auth: keys.auth ?? "" },
      });
      state.value = error ? "idle" : "enabled";
    } catch {
      state.value = "idle";
    }
  }

  return { supported, state, enable };
}
