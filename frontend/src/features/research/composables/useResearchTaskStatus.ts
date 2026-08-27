// 研究任务实时状态（Phase 3 波7）：SSE 订阅 → 轮询兜底（doc7 §11 模式复用）。
// EventSource 到不了终态（断网/代理不支持流）→ 自动退避轮询 GET /tasks/{id}。
import { onUnmounted, readonly, ref } from "vue";
import client from "@/api/client";
import type { ResearchTask } from "@/features/research/composables/queries";

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

export interface TaskStatusState {
  status: string | null;
  progress: number | null;
  reportId: string | null;
  errorCode: string | null;
  source: "sse" | "polling" | "idle";
}

export function useResearchTaskStatus(taskId: () => string | null) {
  const state = ref<TaskStatusState>({
    status: null, progress: null, reportId: null, errorCode: null, source: "idle",
  });
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

  function apply(t: Partial<ResearchTask>, source: TaskStatusState["source"]) {
    state.value = {
      status: t.status ?? null,
      progress: t.progress ?? null,
      reportId: t.report_id ?? null,
      errorCode: t.error_code ?? null,
      source,
    };
  }

  async function pollOnce() {
    const id = taskId();
    if (!id || disposed) return;
    const { data, error } = await client.GET("/api/v1/research/tasks/{task_id}", {
      params: { path: { task_id: id } },
    });
    if (disposed) return;
    if (data && !error) apply(data, "polling");
    const s = state.value.status;
    if (s && TERMINAL.has(s)) return;
    attempt += 1;
    // 退避 2s/4s/8s 封顶 10s（研究任务长耗时，节奏比 job 轮询慢）
    const delay = Math.min(2000 * 2 ** Math.min(attempt - 1, 2), 10_000);
    timer = setTimeout(pollOnce, delay);
  }

  function start() {
    stop();
    attempt = 0;
    disposed = false;
    const id = taskId();
    if (!id) return;
    try {
      es = new EventSource(`/api/v1/research/tasks/${id}/events`, {
        withCredentials: true,
      });
      es.onmessage = (ev) => {
        try {
          const p = JSON.parse(ev.data) as {
            status?: string; progress?: number;
            report_id?: string | null; error_code?: string | null;
          };
          apply(
            {
              status: p.status,
              progress: p.progress,
              report_id: p.report_id,
              error_code: p.error_code,
            } as Partial<ResearchTask>,
            "sse",
          );
          if (p.status && TERMINAL.has(p.status)) stop();
        } catch {
          /* 非 JSON 事件忽略 */
        }
      };
      es.onerror = () => {
        // SSE 断开：若未到终态转入轮询兜底
        stop();
        if (!disposed && !TERMINAL.has(state.value.status ?? "")) {
          attempt = 0;
          pollOnce();
        }
      };
    } catch {
      pollOnce(); // EventSource 不可用（如测试环境）
    }
  }

  onUnmounted(() => {
    disposed = true;
    stop();
  });

  return { state: readonly(state), start, stop };
}
