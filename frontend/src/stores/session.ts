import { defineStore } from "pinia";
import { ref } from "vue";

export const useSessionStore = defineStore("session", () => {
  const userIdHash = ref<string | null>(null);
  const isAuthenticated = ref(false);

  async function fetchSession(): Promise<void> {
    try {
      const r = await fetch("/api/v1/auth/session", { credentials: "same-origin" });
      if (r.ok) {
        const data = (await r.json()) as { user_id_hash: string };
        userIdHash.value = data.user_id_hash;
        isAuthenticated.value = true;
      } else {
        isAuthenticated.value = false;
        userIdHash.value = null;
      }
    } catch {
      isAuthenticated.value = false;
    }
  }

  function setAuthenticated(uid: string): void {
    userIdHash.value = uid;
    isAuthenticated.value = true;
  }

  function clear(): void {
    userIdHash.value = null;
    isAuthenticated.value = false;
  }

  return { userIdHash, isAuthenticated, fetchSession, setAuthenticated, clear };
});
