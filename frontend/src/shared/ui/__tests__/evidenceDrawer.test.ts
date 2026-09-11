// EvidenceDrawer（W2.5-1）：列表渲染 + 背景点击关闭 + 展开加载证据详情。
import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mockClient = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock("@/api/client", () => ({ default: mockClient }));

import EvidenceDrawer from "@/shared/ui/EvidenceDrawer.vue";

const CITATIONS = [
  { evidence_id: "ev1", locator: "para:1", verified: true, content_hash: "abc123" },
  { evidence_id: "ev2", locator: "para:2", verified: false, unverified_note: "单源引用" },
];

function mountDrawer(open = true) {
  return mount(EvidenceDrawer, {
    props: { open, citations: CITATIONS, title: "600519 研究报告" },
    attachTo: document.body,
  });
}

describe("EvidenceDrawer", () => {
  it("open 时渲染引用条目与验证徽章；closed 不渲染（Teleport 内容查 document）", () => {
    const w = mountDrawer();
    expect(document.querySelector('[data-testid="evidence-drawer"]')).not.toBeNull();
    const items = document.querySelectorAll('[data-testid^="evidence-item-"]');
    expect(items.length).toBe(2);
    expect(document.body.textContent).toContain("已双源验证");
    expect(document.body.textContent).toContain("未验证");
    w.unmount(); // 卸载同时移除 Teleport 节点
    const closed = mount(EvidenceDrawer, {
      props: { open: false, citations: CITATIONS },
      attachTo: document.body,
    });
    expect(document.querySelector('[data-testid="evidence-drawer"]')).toBeNull();
    closed.unmount();
  });

  it("点击条目展开并经 evidence API 拉取原文详情", async () => {
    mockClient.GET.mockImplementation(async (_path: string, opts: { params: { path: { evidence_id?: string; document_id?: string } } }) => {
      if (_path.includes("evidence") && opts.params.path.evidence_id === "ev1") {
        return {
          data: { id: "ev1", document_id: "doc1", claim_text: "营业收入增长15%", trust_level: "L1", cited_at: null },
          error: null,
        };
      }
      if (opts.params.path.document_id === "doc1") {
        return { data: { id: "doc1", title: "600519 年度报告", source_url: "https://x" }, error: null };
      }
      return { data: undefined, error: { detail: "nf" } };
    });
    const w = mountDrawer();
    const item = document.querySelector('[data-testid="evidence-item-0"]') as HTMLButtonElement;
    item.click();
    await flushPromises();
    const detail = document.querySelector('[data-testid="evidence-detail"]');
    expect(detail).not.toBeNull();
    expect(detail?.textContent).toContain("600519 年度报告");
    expect(detail?.textContent).toContain("营业收入增长15%");
    w.unmount();
  });

  it("点击背景关闭（emit close）", async () => {
    const w = mountDrawer();
    (document.querySelector('[data-testid="evidence-backdrop"]') as HTMLElement).click();
    await flushPromises();
    expect(w.emitted("close")).toHaveLength(1);
    w.unmount();
  });
});
