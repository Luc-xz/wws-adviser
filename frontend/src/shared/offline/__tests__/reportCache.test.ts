// 报告私有离线缓存契约（Phase 3.4，doc7 §5）：user 隔离 / 版本化 / LRU 上限 / 登出清空。
import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  putReport,
  getCachedReport,
  clearAllReportCaches,
  REPORT_CACHE_LIMIT,
} from "@/shared/offline/reportCache";

// —— 假 Cache Storage（jsdom 无实现）——
class FakeCache implements Cache {
  private map = new Map<string, string>();
  async match(url: string): Promise<Response | undefined> {
    const body = this.map.get(url);
    return body === undefined ? undefined : new Response(body);
  }
  async put(url: string, response: Response): Promise<void> {
    this.map.delete(url);
    this.map.set(url, await response.text()); // 重复 put 刷新插入顺序（LRU 依据）
  }
  async keys(): Promise<Request[]> {
    return [...this.map.keys()].map((u) => new Request(u));
  }
  async delete(url: string | Request): Promise<boolean> {
    const key = typeof url === "string" ? url : url.url;
    return this.map.delete(key);
  }
  add(): Promise<void> {
    throw new Error("unused");
  }
  addAll(): Promise<void> {
    throw new Error("unused");
  }
  matchAll(): Promise<Response[]> {
    throw new Error("unused");
  }
}

function fakeCaches() {
  const caches = new Map<string, FakeCache>();
  const storage = {
    open: async (name: string) => {
      if (!caches.has(name)) caches.set(name, new FakeCache());
      return caches.get(name)!;
    },
    keys: async () => [...caches.keys()],
    delete: async (name: string) => caches.delete(name),
  };
  return { storage, caches };
}

let env: ReturnType<typeof fakeCaches>;
beforeEach(() => {
  env = fakeCaches();
  vi.stubGlobal("caches", env.storage);
});

describe("reportCache", () => {
  it("put 后可读回，cached_at 为 ISO 时间", async () => {
    await putReport({ userKey: "u1", kind: "daily", reportId: "r1", version: "3", payload: { a: 1 } });
    const hit = await getCachedReport<{ a: number }>({ userKey: "u1", kind: "daily", reportId: "r1" });
    expect(hit).not.toBeNull();
    expect(hit!.payload).toEqual({ a: 1 });
    expect(hit!.version).toBe("3");
    expect(Number.isNaN(Date.parse(hit!.cached_at))).toBe(false);
  });

  it("user 隔离：u2 读不到 u1 的缓存", async () => {
    await putReport({ userKey: "u1", kind: "daily", reportId: "r1", version: "1", payload: {} });
    const hit = await getCachedReport({ userKey: "u2", kind: "daily", reportId: "r1" });
    expect(hit).toBeNull();
  });

  it("kind 隔离：daily 与 research 同 id 互不串", async () => {
    await putReport({ userKey: "u1", kind: "daily", reportId: "x", version: "1", payload: { d: 1 } });
    await putReport({ userKey: "u1", kind: "research", reportId: "x", version: "1", payload: { r: 1 } });
    const d = await getCachedReport({ userKey: "u1", kind: "daily", reportId: "x" });
    const r = await getCachedReport({ userKey: "u1", kind: "research", reportId: "x" });
    expect(d!.payload).toEqual({ d: 1 });
    expect(r!.payload).toEqual({ r: 1 });
  });

  it("版本化：读最高版本", async () => {
    await putReport({ userKey: "u1", kind: "daily", reportId: "r1", version: "1", payload: { v: 1 } });
    await putReport({ userKey: "u1", kind: "daily", reportId: "r1", version: "5", payload: { v: 5 } });
    await putReport({ userKey: "u1", kind: "daily", reportId: "r1", version: "3", payload: { v: 3 } });
    const hit = await getCachedReport<{ v: number }>({ userKey: "u1", kind: "daily", reportId: "r1" });
    expect(hit!.payload).toEqual({ v: 5 });
  });

  it("LRU：超上限删最旧", async () => {
    for (let i = 0; i < REPORT_CACHE_LIMIT + 3; i++) {
      await putReport({ userKey: "u1", kind: "daily", reportId: `r${i}`, version: "1", payload: i });
    }
    const oldest = await getCachedReport({ userKey: "u1", kind: "daily", reportId: "r0" });
    expect(oldest).toBeNull();
    const newest = await getCachedReport<{ i: number }>({
      userKey: "u1", kind: "daily", reportId: `r${REPORT_CACHE_LIMIT + 2}`,
    });
    expect(newest!.payload).toBe(REPORT_CACHE_LIMIT + 2);
  });

  it("登出清空：只清 wws-report-* 前缀缓存", async () => {
    await putReport({ userKey: "u1", kind: "daily", reportId: "r1", version: "1", payload: {} });
    await env.storage.open("assets"); // 静态资源缓存不受影响
    await clearAllReportCaches();
    const hit = await getCachedReport({ userKey: "u1", kind: "daily", reportId: "r1" });
    expect(hit).toBeNull();
    expect((await env.storage.keys()).includes("assets")).toBe(true);
  });
});
