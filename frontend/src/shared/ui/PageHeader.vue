<script setup lang="ts">
// 页面标题区（UI §5.3，波 V2）：标题 + 一行辅助说明 + 最多 1 主 1 次操作位。
// 移动端主操作右上角或内容区全宽按钮——通过 actions 槽由页面决定。
defineProps<{
  title: string
  subtitle?: string
  /** 二级页：显示返回箭头（配合 router.back()） */
  back?: boolean
}>();

const emit = defineEmits<{ back: [] }>();
</script>

<template>
  <div class="mb-4 flex items-start justify-between gap-3">
    <div class="flex min-w-0 items-start gap-2">
      <button
        v-if="back"
        type="button"
        class="mt-0.5 appearance-none rounded-md bg-transparent p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700"
        aria-label="返回"
        data-testid="page-back"
        @click="emit('back')"
      >
        <span
          class="i-carbon-arrow-left inline-block h-5 w-5 leading-none"
          aria-hidden="true"
        />
      </button>
      <div class="min-w-0">
        <h1 class="truncate text-h1 font-bold lg:text-h1-d">
          {{ title }}
        </h1>
        <p
          v-if="subtitle"
          class="mt-0.5 text-label text-gray-500 dark:text-gray-400"
        >
          {{ subtitle }}
        </p>
      </div>
    </div>
    <div
      v-if="$slots.actions"
      class="flex shrink-0 items-center gap-2"
    >
      <slot name="actions" />
    </div>
  </div>
</template>
