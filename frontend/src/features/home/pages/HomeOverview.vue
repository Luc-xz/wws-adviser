<!-- HOME-01 首页总览（Phase 0 占位 + stub 行情闭环验证） -->
<script setup lang="ts">
import { onMounted, ref } from "vue";

import { formatMoney, formatPercent } from "@/shared/format/number";

const quote = ref<{
  code: string;
  source: string;
  price: string;
  change_pct: string;
} | null>(null);
const error = ref("");

// 前后端闭环：通过后端 API 拿 stub 行情，证明 stub→domain→API→前端通
onMounted(async () => {
  try {
    const r = await fetch("/api/v1/market-data/quotes/600519", {
      credentials: "same-origin",
    });
    if (r.ok) quote.value = await r.json();
    else error.value = "行情获取失败";
  } catch {
    error.value = "服务不可用";
  }
});
</script>

<template>
  <section>
    <h1>首页</h1>
    <p class="text-tertiary">
      HOME-01 首页总览（Phase 1 完整实现）
    </p>

    <div
      v-if="quote"
      class="quote num"
      data-num
    >
      <div class="code">
        {{ quote.code }}
      </div>
      <div class="price">
        {{ formatMoney(quote.price) }}
      </div>
      <div class="change">
        {{ formatPercent(quote.change_pct) }}
      </div>
      <div class="text-online">
        来源 {{ quote.source }}
      </div>
    </div>
    <p
      v-else-if="error"
      class="text-error"
    >
      {{ error }}
    </p>
    <p
      v-else
      class="text-tertiary"
    >
      加载中...
    </p>
  </section>
</template>

<style scoped>
.quote {
  margin-top: 16px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e4e7ec;
  border-radius: 8px;
}
.code {
  font-weight: 600;
}
.price {
  font-size: 24px;
  font-weight: 700;
}
</style>
