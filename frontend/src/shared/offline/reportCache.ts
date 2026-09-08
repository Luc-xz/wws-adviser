// 报告私有离线缓存（Phase 3.4，doc7 §5）：Cache Storage 按 user 隔离 + 版本化 key。
//
// - 隔离：缓存名 `wws-report-{userKey}`（userKey = user_id_hash）；换用户互不可见。
// - 版本：key 携带 `?v={version}`；读取取最大版本（报告不可变，新版本=新行）。
// - 上限：单用户 LRU 10 份（"离线报告缓存数量上限：按设备存储定"——留常量可调）。
// - 登出：clearAllReportCaches() 清全部 wws-report-*（doc7 §3 规则 3）。
// - 边界：盘中行情/建议不入本缓存（SW NetworkOnly，doc7 §5 表）。
//
// jsdom 无 Cache Storage——经 CACHE_STORAGE 注入桩以便单测。

export type ReportKind = "daily" | "research";

export interface CachedReport<T = unknown> {
  payload: T;
  version: string;
  cached_at: string; // ISO——离线横幅"缓存于"时间
}

interface CacheLike {
  match(url: string): Promise<Response | undefined>;
  put(url: string, response: Response): Promise<void>;
  keys(): Promise<Request[]>;
  delete(url: string | Request): Promise<boolean>;
}

interface CacheStorageLike {
  open(name: string): Promise<CacheLike>;
  keys(): Promise<string[]>;
  delete(name: string): Promise<boolean>;
}

declare global {
  interface Window {
    caches?: CacheStorageLike;
  }
}

export const REPORT_CACHE_PREFIX = "wws-report-";
export const REPORT_CACHE_LIMIT = 10;

function storage(): CacheStorageLike {
  const s = (typeof window !== "undefined" ? window.caches : undefined) ?? undefined;
  if (!s) throw new Error("Cache Storage 不可用（无窗口或未实现）");
  return s;
}

function cacheName(userKey: string): string {
  return `${REPORT_CACHE_PREFIX}${userKey}`;
}

function entryUrl(kind: ReportKind, reportId: string, version: string): string {
  // Cache API 按 URL 匹配：用伪 origin 承载 key，查询串带版本。
  return `https://wws.local/${kind}-report/${reportId}?v=${encodeURIComponent(version)}`;
}

function parseEntry(url: string): { kind: string; reportId: string; version: number } | null {
  const m = url.match(/\/(daily|research)-report\/([^?]+)\?v=(\d+)$/);
  return m ? { kind: m[1], reportId: m[2], version: Number(m[3]) } : null;
}

/** 网络成功后写入（含 cached_at 信封）。LRU 超限删最旧。 */
export async function putReport<T>(opts: {
  userKey: string;
  kind: ReportKind;
  reportId: string;
  version: string;
  payload: T;
}): Promise<void> {
  const cache = await storage().open(cacheName(opts.userKey));
  const envelope: CachedReport<T> = {
    payload: opts.payload,
    version: opts.version,
    cached_at: new Date().toISOString(),
  };
  await cache.put(
    entryUrl(opts.kind, opts.reportId, opts.version),
    new Response(JSON.stringify(envelope), {
      headers: { "content-type": "application/json" },
    })
  );
  // LRU：keys 顺序即插入/最近使用顺序（put 刷新位置），超限删最旧
  const keys = await cache.keys();
  if (keys.length > REPORT_CACHE_LIMIT) {
    for (const k of keys.slice(0, keys.length - REPORT_CACHE_LIMIT)) {
      await cache.delete(k);
    }
  }
}

/** 读某报告的最高版本缓存；无 → null。 */
export async function getCachedReport<T>(opts: {
  userKey: string;
  kind: ReportKind;
  reportId: string;
}): Promise<CachedReport<T> | null> {
  const cache = await storage().open(cacheName(opts.userKey));
  const entries: { url: string; version: number }[] = [];
  for (const req of await cache.keys()) {
    const parsed = parseEntry(req.url);
    if (parsed?.kind === opts.kind && parsed.reportId === opts.reportId) {
      entries.push({ url: req.url, version: parsed.version });
    }
  }
  if (!entries.length) return null;
  entries.sort((a, b) => b.version - a.version);
  const hit = await cache.match(entries[0].url);
  if (!hit) return null;
  return (await hit.json()) as CachedReport<T>;
}

/** 登出/清除本机数据：清该用户（或全部 wws-report-*）私有缓存。 */
export async function clearAllReportCaches(): Promise<void> {
  const names = await storage().keys();
  await Promise.all(
    names.filter((n) => n.startsWith(REPORT_CACHE_PREFIX)).map((n) => storage().delete(n))
  );
}
