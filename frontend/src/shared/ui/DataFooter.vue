<script setup lang="ts">
// 数据尾注（ENFORCEMENT_CONTRACT §2.3）：截至/来源/有效期——行情/建议/报告块必带
defineProps<{
  asOf?: string | null; // 截至（业务日期/时间）
  source?: string | null; // 来源
  validUntil?: string | null; // 有效期（建议类）
}>();
</script>

<template>
  <div
    class="mt-1 text-xs text-gray-400 dark:text-gray-500"
    data-testid="data-footer"
  >
    <span v-if="asOf">截至 {{ asOf }}</span>
    <span v-if="source"> · 来源 {{ source }}</span>
    <span v-if="validUntil"> · 有效期至 {{ validUntil }}</span>
  </div>
</template>
