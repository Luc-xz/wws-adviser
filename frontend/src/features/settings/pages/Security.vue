<script setup lang="ts">
// SET-06 安全与会话（波 V4，计划 §5 V4 序 8）：Passkey 管理（列表/注册/删除）
// + 改密码 + 登出。sessions 全列 API 后端缺（计划注明），先交付 Passkey 主线。
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";
import { clearAllReportCaches } from "@/shared/offline/reportCache";
import { useSessionStore } from "@/stores/session";

const router = useRouter();
const qc = useQueryClient();
const session = useSessionStore();

interface Passkey {
  id: string;
  name: string;
  sign_count: number;
  created_at: string;
  last_used_at: string | null;
}

const keys = ref<Passkey[]>([]);
const loading = ref(true);
const regState = ref<"idle" | "working" | "done" | "error">("idle");
const regError = ref("");

async function loadKeys() {
  loading.value = true;
  try {
    const { data, error } = await client.GET("/api/v1/auth/passkey/credentials");
    if (!error && data) keys.value = data as Passkey[];
  } finally {
    loading.value = false;
  }
}
onMounted(loadKeys);

function b64ToBuffer(base64: string): ArrayBuffer {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes.buffer as ArrayBuffer;
}

/** 注册流程：后端 options → navigator.credentials.create → verify */
async function registerPasskey() {
  regState.value = "working";
  regError.value = "";
  try {
    const { data: opt, error: e1 } = await client.POST("/api/v1/auth/passkey/register/options", {
      params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    });
    if (e1 || !opt) throw new Error(String((e1 as { message?: string })?.message ?? "options 获取失败"));
    const options = (opt as { options: Record<string, unknown> }).options;
    const pk = options.publicKey as Record<string, unknown>;
    // b64url 字段转 BufferSource（WebAuthn API 要求）
    if (pk.challenge) pk.challenge = b64ToBuffer(pk.challenge as string);
    const user = pk.user as Record<string, unknown>;
    if (user?.id) user.id = b64ToBuffer(user.id as string);
    const cred = (await navigator.credentials.create({ publicKey: pk as unknown as PublicKeyCredentialCreationOptions })) as PublicKeyCredential;
    const response = cred.response as AuthenticatorAttestationResponse;
    const enc = (b: ArrayBuffer) =>
      btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const { error: e2 } = await client.POST("/api/v1/auth/passkey/register/verify", {
      params: { header: { "Idempotency-Key": crypto.randomUUID() } },
      body: {
        id: cred.id,
        rawId: cred.id,
        type: cred.type,
        response: {
          clientDataJSON: enc(response.clientDataJSON),
          attestationObject: enc(response.attestationObject),
        },
        transports: response.getTransports?.() ?? [],
        name: `Passkey ${new Date().toLocaleDateString()}`,
      },
    });
    if (e2) throw new Error("注册校验失败");
    regState.value = "done";
    await loadKeys();
  } catch (e) {
    regState.value = "error";
    regError.value = e instanceof Error ? e.message : "注册失败（需 HTTPS 与浏览器支持）";
  }
}

async function removeKey(credentialId: string) {
  await client.DELETE("/api/v1/auth/passkey/credentials/{credential_id}", {
    params: { path: { credential_id: credentialId } },
  });
  await loadKeys();
}

// —— 改密码 ——
const oldPw = ref("");
const newPw = ref("");
const pwMsg = ref("");
const pwOk = ref(false);

async function changePassword() {
  pwMsg.value = "";
  const { error } = await client.POST("/api/v1/auth/password", {
    body: { old_password: oldPw.value, new_password: newPw.value },
  });
  if (error) {
    pwOk.value = false;
    pwMsg.value = "修改失败——检查旧密码或新密码强度";
    return;
  }
  pwOk.value = true;
  pwMsg.value = "已修改，其他会话已撤销";
  oldPw.value = newPw.value = "";
}

async function logoutAll() {
  await client.POST("/api/v1/auth/logout");
  session.clear();
  qc.clear();
  await clearAllReportCaches().catch(() => undefined);
  router.push({ name: "login" });
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="安全与会话"
      subtitle="Passkey · 改密码（撤销其他会话）· 登出"
      back
      @back="router.back()"
    />

    <!-- Passkey 管理 -->
    <section class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
      <div class="flex items-center justify-between">
        <h2 class="text-h3 font-semibold">
          Passkey
        </h2>
        <button
          type="button"
          class="appearance-none rounded-md bg-primary px-3 py-1.5 text-label font-medium text-white disabled:opacity-40"
          :disabled="regState === 'working'"
          data-testid="passkey-register"
          @click="registerPasskey"
        >
          {{ regState === "working" ? "注册中…" : "注册本机 Passkey" }}
        </button>
      </div>
      <p
        v-if="regState === 'error'"
        class="mt-2 text-caption text-error"
      >
        {{ regError }}
      </p>
      <p
        v-if="loading"
        class="mt-2 text-caption text-gray-400"
      >
        加载中…
      </p>
      <p
        v-else-if="!keys.length"
        class="mt-2 text-caption text-gray-400 dark:text-gray-500"
      >
        尚未注册——Passkey 与密码登录同权（3_API §3.1）。
      </p>
      <div
        v-for="k in keys"
        :key="k.id"
        class="mt-2 flex items-center justify-between border-t border-gray-100 pt-2 dark:border-gray-700"
      >
        <div class="min-w-0">
          <div class="truncate text-body font-medium">
            {{ k.name }}
          </div>
          <div
            class="text-caption text-gray-400 num dark:text-gray-500"
            data-num
          >
            {{ k.created_at.slice(0, 10) }} 注册 · 计数 {{ k.sign_count }}
            {{ k.last_used_at ? `· 最近使用 ${k.last_used_at.slice(0, 10)}` : "" }}
          </div>
        </div>
        <button
          type="button"
          class="shrink-0 appearance-none rounded px-2 py-1 text-caption text-gray-500 hover:text-error dark:text-gray-400"
          @click="removeKey(k.id)"
        >
          删除
        </button>
      </div>
    </section>

    <!-- 改密码 -->
    <section class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
      <h2 class="text-h3 font-semibold">
        修改密码
      </h2>
      <form
        class="mt-2 space-y-3"
        @submit.prevent="changePassword"
      >
        <input
          v-model="oldPw"
          type="password"
          placeholder="当前密码"
          autocomplete="current-password"
          class="w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body dark:border-gray-700"
        >
        <input
          v-model="newPw"
          type="password"
          placeholder="新密码（支持长密码）"
          autocomplete="new-password"
          class="w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body dark:border-gray-700"
        >
        <p
          v-if="pwMsg"
          class="text-caption"
          :class="pwOk ? 'text-success' : 'text-error'"
        >
          {{ pwMsg }}
        </p>
        <button
          type="submit"
          class="w-full appearance-none rounded-md border border-primary py-2 text-body font-medium text-primary"
        >
          修改密码
        </button>
      </form>
    </section>

    <button
      type="button"
      class="w-full appearance-none rounded-lg border border-gray-200 py-3 text-body font-medium text-gray-600 dark:border-gray-700 dark:text-gray-300"
      data-testid="security-logout"
      @click="logoutAll"
    >
      退出登录（并清除本机离线报告缓存）
    </button>
  </div>
</template>
