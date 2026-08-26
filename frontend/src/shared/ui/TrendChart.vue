<script setup lang="ts">
// 通用趋势折线图（技术债清理：波7 ECharts 留白）。
// echarts/core 按需引入控制包体；深色随 <html class="dark"> 切换重渲。
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
// SVG 渲染器：hidpi 清晰 + jsdom（单测）无需真实 canvas
import { SVGRenderer } from "echarts/renderers";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { isDark } from "@/shared/theme";

echarts.use([LineChart, GridComponent, TooltipComponent, SVGRenderer]);

const props = defineProps<{
  dates: string[];
  values: number[];
  label?: string;
}>();

const el = ref<HTMLDivElement | null>(null);
// ReturnType 规避 core 包类型导出差异
let chart: ReturnType<typeof echarts.init> | null = null;

function axisColor(): string {
  return isDark.value ? "#98a2b3" : "#667085";
}
function lineColor(): string {
  return isDark.value ? "#232936" : "#f2f4f7";
}

function render(): void {
  if (!el.value) return;
  chart ??= echarts.init(el.value);
  chart.setOption({
    grid: { left: 8, right: 8, top: 20, bottom: 0, containLabel: true },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: props.dates,
      axisLabel: { color: axisColor(), fontSize: 11 },
      axisLine: { lineStyle: { color: lineColor() } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      splitLine: { lineStyle: { color: lineColor() } },
      axisLabel: { color: axisColor(), fontSize: 11 },
    },
    series: [
      {
        name: props.label ?? "",
        type: "line",
        data: props.values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, color: "#3157d5" },
        areaStyle: { opacity: 0.08, color: "#3157d5" },
      },
    ],
  });
}

function onResize(): void {
  chart?.resize();
}

onMounted(() => {
  render();
  window.addEventListener("resize", onResize);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  chart?.dispose();
  chart = null;
});
watch(() => [props.dates, props.values] as const, () => render());
watch(isDark, () => {
  chart?.clear();
  render();
});
</script>

<template>
  <div
    ref="el"
    class="h-40 w-full"
  />
</template>
