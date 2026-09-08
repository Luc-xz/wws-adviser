// 研究模块前端测试（Phase 3 波7）：md 渲染转义 + Library 页面骨架。
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { renderReportMd } from "@/features/research/composables/renderMd";

describe("renderReportMd", () => {
  it("渲染标题/引用/表格，且 HTML 全文转义", () => {
    const md = [
      "# 公司研究报告：600519",
      "",
      "## 财务与经营指标【事实】",
      "",
      "收入稳健 <b>增长</b>。",
      "",
      "> 引用[1] 半年报#para:1（单源引用，未经双源验证）",
      "",
      "| 指标 | 当前值 |",
      "| --- | --- |",
      "| 营业收入 | 100.5 |",
    ].join("\n");
    const html = renderReportMd(md);
    expect(html).toContain("<h1>公司研究报告：600519</h1>");
    expect(html).toContain("<h2>财务与经营指标【事实】</h2>");
    expect(html).toContain("&lt;b&gt;增长&lt;/b&gt;"); // 不允许裸 HTML
    expect(html).toContain("<blockquote>");
    expect(html).toContain("<th>指标</th>");
    expect(html).toContain("<td>100.5</td>");
  });
});

// —— Library 页面 ——

const mockQueries = vi.hoisted(() => ({
  useResearchTasks: vi.fn(),
  useResearchReport: vi.fn(),
  useCreateResearchTask: vi.fn(),
  useCancelResearchTask: vi.fn(),
  researchExportUrl: (id: string, f: string) => `/api/v1/research/reports/${id}/export?format=${f}`,
}));

vi.mock("@/features/research/composables/queries", () => mockQueries);
vi.mock("@/features/research/composables/useResearchTaskStatus", () => ({
  useResearchTaskStatus: () => ({
    state: {
      value: { status: null, progress: null, reportId: null, errorCode: null, source: "idle" },
    },
    start: vi.fn(),
    stop: vi.fn(),
  }),
}));

import { ref } from "vue";
import Library from "@/features/research/pages/Library.vue";

function mkRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/research", component: Library },
      { path: "/", component: { template: "<div/>" } },
    ],
  });
}

function mountPage() {
  return mount(Library, { global: { plugins: [mkRouter()] } });
}

describe("Library（研究与报告库）", () => {
  beforeEach(() => {
    mockQueries.useResearchTasks.mockReturnValue({
      data: ref(null), isLoading: ref(false),
    });
    mockQueries.useResearchReport.mockReturnValue({
      data: ref(null), isLoading: ref(false),
    });
    mockQueries.useCreateResearchTask.mockReturnValue({
      create: vi.fn().mockResolvedValue({ id: "t1" }),
    });
    mockQueries.useCancelResearchTask.mockReturnValue({ cancel: vi.fn() });
  });

  it("空态显示引导文案；表单元素齐全", () => {
    const w = mountPage();
    expect(w.find('[data-testid="research-create-form"]').exists()).toBe(true);
    expect(w.find('[data-testid="research-subject-input"]').exists()).toBe(true);
    expect(w.find('[data-testid="research-depth-select"]').exists()).toBe(true);
    expect(w.text()).toContain("暂无研究任务");
  });

  it("任务列表渲染状态徽章与失败原因；完成态显示报告面板", async () => {
    mockQueries.useResearchTasks.mockReturnValue({
      data: ref({
        items: [
          { id: "t1", task_type: "company", subject: "600519", depth: "standard",
            status: "COMPLETED", progress: 100, error_code: null,
            report_id: "r1", created_at: "2026-08-27" },
          { id: "t2", task_type: "industry", subject: "白酒", depth: "quick",
            status: "FAILED", progress: 30,
            error_code: "insufficient_evidence", report_id: null,
            created_at: "2026-08-27" },
        ],
      }),
      isLoading: ref(false),
    });
    mockQueries.useResearchReport.mockReturnValue({
      data: ref({
        id: "r1", content_md: "# 公司研究报告：600519\n\n## 概览【事实】",
        citations: [{
          evidence_id: "e1", section: "overview", locator: "半年报#para:1",
          content_hash: "abc", verified: false,
          unverified_note: "单源引用，未经双源验证",
        }],
      }),
      isLoading: ref(false),
    });
    const w = mountPage();
    await flushPromises();

    expect(w.findAll('[data-testid="research-task-row"]').length).toBe(2);
    expect(w.text()).toContain("已完成");
    expect(w.text()).toContain("未检索到证据");

    // 点选完成任务 → 显示报告面板 + 引用清单 + 导出链接
    await w.findAll('[data-testid="research-task-row"]')[0]!.trigger("click");
    await flushPromises();
    expect(w.find('[data-testid="research-report-panel"]').exists()).toBe(true);
    expect(w.find('[data-testid="research-citations"]').text()).toContain("半年报#para:1");
    expect(w.html()).toContain("/api/v1/research/reports/r1/export?format=md");
    // 认知层级标签在渲染后的报告里
    expect(w.html()).toContain("概览【事实】");
  });
});
