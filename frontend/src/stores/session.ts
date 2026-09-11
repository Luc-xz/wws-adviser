import { defineStore } from "pinia";
import { ref } from "vue";
import client from "@/api/client";

// W4 E2E 发现的真缺陷修复：userIdHash 此前仅存内存——真离线重载后
// /auth/session 失败 → 哈希丢失 → 私有报告缓存（按 user_id_hash 隔离）打不开，
// AC-08"离线可打开最近报告"在重载场景不成立。
// 修复：哈希持久化 sessionStorage（会话级：标签页关闭即清，登出显式清除，
// 不留跨会话数据）；fetchSession 网络失败（离线）时保留恢复出的状态——
// 只有服务端明确未认证才清除（离线 ≠ 登出）。
const UID_KEY = "wws-uid-hash";

function restoreUid(): string | null {
  try {
    return sessionStorage.getItem(UID_KEY);
  } catch {
    return null; // 隐私模式等 storage 不可用场景：退化为内存态
  }
}

function persistUid(uid: string | null): void {
  try {
    if (uid) sessionStorage.setItem(UID_KEY, uid);
    else sessionStorage.removeItem(UID_KEY);
  } catch {
    /* ignore */
  }
}

export const useSessionStore = defineStore("session", () => {
  const userIdHash = ref<string | null>(restoreUid());
  const isAuthenticated = ref(userIdHash.value !== null);

  async function fetchSession(): Promise<void> {
    try {
      const { data, error } = await client.GET("/api/v1/auth/session");
      if (!error && data) {
        setAuthenticated(data.user_id_hash);
      } else {
        clear();
      }
    } catch {
      // 网络失败（离线）：保留恢复出的会话状态（离线 ≠ 登出）
    }
  }

  function setAuthenticated(uid: string): void {
    userIdHash.value = uid;
    isAuthenticated.value = true;
    persistUid(uid);
  }

  function clear(): void {
    userIdHash.value = null;
    isAuthenticated.value = false;
    persistUid(null);
  }

  return { userIdHash, isAuthenticated, fetchSession, setAuthenticated, clear };
});
