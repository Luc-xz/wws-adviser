// useJobStatus 契约（doc7 §11）：SSE 不可用 → 退避轮询兜底；终态停止轮询。
// 通过 vi.mock 屏蔽 typed client；EventSource 用桩（立即 error → 走轮询路径）。
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ref } from "vue";

const mockGet = vi.hoisted(() => vi.fn());
vi.mock("@/api/client", () => ({
  default: { GET: mockGet },
}));

import { useJobStatus } from "@/shared/sse/useJobStatus";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(
    public url: string,
    _opts?: { withCredentials?: boolean }
  ) {
    FakeEventSource.instances.push(this);
  }
  close() {
    this.onmessage = null;
    this.onerror = null;
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  mockGet.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useJobStatus 轮询兜底", () => {
  it("SSE 不可用（onerror）→ 退避轮询 GET /jobs/{id}，终态后停止", async () => {
    mockGet.mockResolvedValue({ data: { status: "RUNNING", progress: 10 }, error: undefined });
    const jobId = ref<string | null>("job-1");
    const { state, start } = useJobStatus(() => jobId.value);
    start();

    // SSE 立即失败 → 触发轮询（第一拍）
    FakeEventSource.instances[0]?.onerror?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet.mock.calls[0][0]).toBe("/api/v1/jobs/{job_id}");
    expect(state.value.source).toBe("polling");
    expect(state.value.status).toBe("RUNNING");

    // 退避第二拍
    await vi.advanceTimersByTimeAsync(1000);
    expect(mockGet).toHaveBeenCalledTimes(2);

    // 终态 → 停止
    mockGet.mockResolvedValue({ data: { status: "COMPLETED", progress: 100 }, error: undefined });
    await vi.advanceTimersByTimeAsync(2000);
    expect(state.value.status).toBe("COMPLETED");
    const calls = mockGet.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(mockGet.mock.calls.length).toBe(calls); // 不再轮询
  });

  it("SSE 事件命中同 job → 更新状态并停止", async () => {
    mockGet.mockResolvedValue({ data: { status: "RUNNING" }, error: undefined });
    const jobId = ref<string | null>("job-9");
    const { state, start } = useJobStatus(() => jobId.value);
    start();
    const es = FakeEventSource.instances[0];
    es?.onmessage?.({
      data: JSON.stringify({ event: "job", job_id: "job-9", status: "COMPLETED", progress: 100, ts: "t" }),
    });
    expect(state.value.source).toBe("sse");
    expect(state.value.status).toBe("COMPLETED");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(mockGet).not.toHaveBeenCalled(); // SSE 已终态，无需轮询
  });
});
