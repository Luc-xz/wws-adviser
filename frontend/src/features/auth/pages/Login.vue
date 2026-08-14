<!-- AUTH-01 登录（typed client → /api/v1/auth/login） -->
<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import client from "@/api/client";
import { useSessionStore } from "@/stores/session";

const username = ref("");
const password = ref("");
const error = ref("");
const loading = ref(false);
const router = useRouter();
const route = useRoute();
const session = useSessionStore();

async function onSubmit(): Promise<void> {
  error.value = "";
  loading.value = true;
  try {
    const { data, error: err } = await client.POST("/api/v1/auth/login", {
      params: { header: { "Idempotency-Key": crypto.randomUUID() } },
      body: { username: username.value, password: password.value },
    });
    if (!err && data) {
      session.setAuthenticated(data.user_id_hash);
      const redirect = (route.query.redirect as string) || "/";
      router.push(redirect);
    } else {
      const status = (err as unknown as { status?: number })?.status;
      if (status === 401) {
        error.value = "用户名或密码错误"; // 不泄露账号是否存在
      } else if (status === 429) {
        error.value = "尝试过多，请稍后再试";
      } else {
        error.value = "服务暂不可用";
      }
    }
  } catch {
    error.value = "网络错误，请检查连接";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-wrap">
    <form
      class="login-card"
      @submit.prevent="onSubmit"
    >
      <h1>WWS Adviser</h1>
      <p class="text-tertiary">
        个人投资顾问
      </p>
      <input
        v-model="username"
        placeholder="用户名"
        autocomplete="username"
        required
      >
      <input
        v-model="password"
        type="password"
        placeholder="密码"
        autocomplete="current-password"
        required
      >
      <button
        type="submit"
        :disabled="loading"
      >
        {{ loading ? "登录中..." : "登录" }}
      </button>
      <p
        v-if="error"
        class="text-error"
        data-testid="login-error"
      >
        {{ error }}
      </p>
    </form>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.login-card {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
input {
  padding: 12px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 16px;
}
button {
  padding: 12px;
  background: #3157d5;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.6;
}
</style>
