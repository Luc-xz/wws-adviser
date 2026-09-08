// 报告查询的离线回退（Phase 3.4）：网络成功写透私有缓存；断网卡死回退最近缓存副本。
// doc7 §5「最近查看的已完成报告：Network First，失败回退私有缓存」。
import { ref, type Ref } from "vue";
import { useSessionStore } from "@/stores/session";
import {
  putReport,
  getCachedReport,
  type CachedReport,
  type ReportKind,
} from "@/shared/offline/reportCache";

export interface OfflineFallback<T> {
  /** 非 null = 当前数据来自离线缓存（值为缓存时间 ISO） */
  offlineCachedAt: Ref<string | null>;
  /** 网络成功路径（写透缓存，失败静默——缓存绝不影响在线读取） */
  writeThrough: (payload: T, version: string) => void;
  /** 断网路径：读缓存命中 → payload + 标记时间；未命中 → null */
  readBack: () => Promise<T | null>;
}

export function useOfflineFallback<T>(kind: ReportKind, reportId: () => string): OfflineFallback<T> {
  const session = useSessionStore();
  const offlineCachedAt = ref<string | null>(null);

  function userKey(): string | null {
    return session.userIdHash ?? null;
  }

  function writeThrough(payload: T, version: string): void {
    const uk = userKey();
    if (!uk) return;
    putReport<T>({ userKey: uk, kind, reportId: reportId(), version, payload }).catch(() => {
      /* 私有缓存失败不影响在线路径（隐私存储满/隐私模式等） */
    });
  }

  async function readBack(): Promise<T | null> {
    const uk = userKey();
    if (!uk) return null;
    try {
      const hit: CachedReport<T> | null = await getCachedReport<T>({
        userKey: uk, kind, reportId: reportId(),
      });
      if (!hit) return null;
      offlineCachedAt.value = hit.cached_at;
      return hit.payload;
    } catch {
      return null; // Cache Storage 不可用（老浏览器）——按无离线副本处理
    }
  }

  return { offlineCachedAt, writeThrough, readBack };
}
