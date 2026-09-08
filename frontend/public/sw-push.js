// Web Push 事件处理（Phase 3.5 P1）——由 workbox generateSW 的 importScripts 注入主 SW。
// payload 契约（backend notifications.service.dispatch_push）：
//   { title, event_type, ...脱敏后的业务摘要 }（FR-NOTIFY-003：锁屏不含标的/金额/动作）
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "通知" };
  }
  const title = data.title || "WWS Adviser";
  const body = data.detail || "点击登录查看详情";
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      tag: data.event_type || "generic",
      data: { url: "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url.includes(self.location.origin)) return client.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
