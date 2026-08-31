// 深色模式（技术债清理：波7 前端留白）。class 策略：<html class="dark">，
// localStorage 持久化；默认跟随系统 prefers-color-scheme。
import { useDark, useToggle } from "@vueuse/core";

export const isDark = useDark({ storageKey: "wws-theme-dark" });
export const toggleDark = useToggle(isDark);
