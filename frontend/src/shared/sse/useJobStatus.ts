// 任务状态订阅（doc7 §11）：先试 EventSource /api/v1/events（Phase 2.2 前不可用）
// → 自动退避轮询 GET /api/v1/jobs/{id} 兜底。事件仅 {event, job_id, status, progress, ts}。
import { readonly, ref, onUnmounted } from "vue";
import client from "@/api/client";

export type JobSource = "sse" | "polling" | "idle";

export interface JobStatusState {
  status: string | null;
  progress: number | null;
  error: string | null;
  source: JobSource;
}

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED", "PARTIAL"]);

export function useJobStatus(jobId: () => string | null) {
  const state = ref<JobStatusState>({ status: null, progress: null, error: null, source: "idle" });
  let es: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let attempt = 0;
  let disposed = false;

  function stop() {
    es?.close();
    es = null;
    if (timer) clearTimeout(timer);
    timer = null;
  }

  async function pollOnce() {
    const id = jobId();
    if (!id) return;
    const { data, error } = await client.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: id } } });
    if (disposed) return;
    if (error || !data) {
      state.value = { ...state.value, error: "任务查询失败" };
    } else {
      state.value = { status: data.status, progress: data.progress ?? null, error: null, source: "polling" };
    }
    const s = state.value.status;
    if (s && TERMINAL.has(s)) return; // 终态停止
    attempt += 1;
    // 退避：1s/2s/4s/8s，封顶 10s
    const delay = Math.min(1000 * 2 ** Math.min(attempt - 1, 3), 10_000);
    timer = setTimeout(pollOnce, delay);
  }

  function start() {
    stop();
    attempt = 0;
    disposed = false;
    const id = jobId();
    if (!id) return;
    // 先试 SSE（带凭据）；onerror → 关闭并落入轮询兜底
    try {
      es = new EventSource("/api/v1/events", { withCredentials: true });
      es.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data) as { job_id?: string; status?: string; progress?: number };
          if (payload.job_id !== id) return;
          state.value = {
            status: payload.status ?? null,
            progress: payload.progress ?? null,
            error: null,
            source: "sse",
          };
          if (payload.status && TERMINAL.has(payload.status)) stop();
        } catch {
          /* 忽略非 JSON 事件 */
        }
      };
      es.onerror = () => {
        // SSE 不可用（当前后端无 /events）→ 轮询兜底
        stop();
        if (!disposed && !state.value.status) void pollOnce();
      };
    } catch {
      void pollOnce();
    }
    // SSE 连接建立期也给轮询兜底打底（若 SSE 3s 内无事件则轮询接管）
    timer = setTimeout(() => {
      if (!disposed && state.value.source !== "sse") {
        es?.close();
        es = null;
        void pollOnce();
      }
    }, 3000);
  }

  onUnmounted(() => {
    disposed = true;
    stop();
  });

  return { state: readonly(state), start, stop };
}
