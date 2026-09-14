<script setup lang="ts">
// 空态插画（W3-B5）：内联 SVG 非 emoji；三种形态（空账户/空列表/无语料）。
// 语义色 + 圆角风格与 material-symbols 视觉语言一致（描边 1.5、圆头、primary 主调）。
withDefaults(
  defineProps<{
    /** empty：空账户/空数据（托盘+光点）；search：无结果（放大镜）；docs：无语料（文档） */
    variant?: "empty" | "search" | "docs";
    size?: number;
  }>(),
  { variant: "empty", size: 96 },
);
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 96 96"
    fill="none"
    aria-hidden="true"
    :data-testid="`empty-illustration-${variant}`"
  >
    <!-- 底盘软阴影圈 -->
    <ellipse
      cx="48"
      cy="82"
      rx="30"
      ry="5"
      class="fill-primary/8 dark:fill-primary/15"
    />

    <template v-if="variant === 'empty'">
      <!-- 空托盘 + 悬浮光点 -->
      <path
        d="M24 54 L34 34 Q35 32 37 32 L59 32 Q61 32 62 34 L72 54"
        class="stroke-primary"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M22 54 H74 Q76 54 75 56 L72 66 Q71 68 69 68 H27 Q25 68 24 66 L21 56 Q20 54 22 54 Z"
        class="fill-primary/10 stroke-primary"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <circle
        cx="48"
        cy="18"
        r="4"
        class="fill-risk-warning/70"
      />
      <circle
        cx="62"
        cy="24"
        r="2.5"
        class="fill-primary/50"
      />
      <circle
        cx="35"
        cy="22"
        r="2"
        class="fill-primary/40"
      />
    </template>

    <template v-else-if="variant === 'search'">
      <!-- 放大镜 + 空结果线 -->
      <circle
        cx="44"
        cy="42"
        r="20"
        class="stroke-primary"
        stroke-width="2.5"
      />
      <path
        d="M59 57 L72 70"
        class="stroke-primary"
        stroke-width="3"
        stroke-linecap="round"
      />
      <path
        d="M36 40 Q40 36 44 40 M50 46 Q54 42 58 46"
        class="stroke-gray-300 dark:stroke-gray-600"
        stroke-width="2"
        stroke-linecap="round"
      />
    </template>

    <template v-else>
      <!-- 文档 + 问号光点（无语料） -->
      <rect
        x="28"
        y="22"
        width="40"
        height="52"
        rx="5"
        class="fill-primary/10 stroke-primary"
        stroke-width="2"
      />
      <path
        d="M38 36 H58 M38 46 H58 M38 56 H52"
        class="stroke-primary/50"
        stroke-width="2.5"
        stroke-linecap="round"
      />
      <circle
        cx="66"
        cy="66"
        r="9"
        class="fill-risk-warning/15 stroke-risk-warning"
        stroke-width="2"
      />
      <path
        d="M63.5 63 Q66 61 68 63 Q69.5 64.5 68 66.5 L66.5 68"
        class="stroke-risk-warning"
        stroke-width="1.8"
        stroke-linecap="round"
      />
      <circle
        cx="66.6"
        cy="71.5"
        r="1.2"
        class="fill-risk-warning"
      />
    </template>
  </svg>
</template>
