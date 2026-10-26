import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LightingRoot } from "@/lib/lighting";
import { LightingArtefactTab } from "../LightingArtefactTab";
import { rowsToCsv } from "../SeriesArtefactTab";

let root: LightingRoot;
let replayed = false;
const registry = { register: vi.fn(), unregister: vi.fn() };
const trigger = vi.fn();
vi.mock("@/providers/SurfaceRegistry", () => ({ useSurfaceState: () => ({ surface: { dataModel: { get: () => root } }, artifact: { replayed } }), useSurfaceRegistry: () => registry }));
vi.mock("@/hooks/useActionDrivenAgent", () => ({ useActionDrivenAgent: () => ({ triggerAction: trigger, cancelAction: vi.fn() }) }));

function fixture(): LightingRoot {
  const row = (id: string, restored: boolean) => ({ id, lamp_id: id, rtu_id: "RTU-017", circuit_id: "2", pole_id: "P-0348", alarm_id: `alarm-${id}`, phase: "A", anchor: "2026-10-25T18:24:00+08:00", evidence_window: { start: "2026-10-25T18:14:00+08:00", end: "2026-10-25T18:34:00+08:00" }, relationship_verified: true, values: { road: restored ? "文昌路" : "滨河路", energy: restored ? null : 0, status_at_cutoff: restored ? "截止时点已解除" : "截止时点未解除" }, evidence: [{ label: "历史功率", value: 0, unit: "W", at: "2026-10-25T18:24:00+08:00", source: "历史巡测", note: "不能单凭 0 W 认定故障" }], missing: [] });
  return { kind: "lighting", scene: "night", title: "整夜单灯运行", status: "partial", error: null, summary: "有一条报警值得核对。", energy_view: null, query: { id: "q1", scope: "全网", timezone: "Asia/Shanghai", window: { start: "2026-10-25T18:00:00+08:00", end: "2026-10-26T07:00:00+08:00" }, rtu_energy_window: null, cutoff: "2026-10-26T07:00:00+08:00", generated_at: "2026-10-26T07:10:00+08:00", basis: "night", source: "合成历史巡测", coverage: "2/2 个对象", filters: ["有样本不等于整晚在线"], missing: ["缺少生产在线判定配置"] }, metrics: [{ label: "报警事件数", value: 2, unit: "条", note: "范围汇总" }], columns: [{ key: "lamp_id", label: "单灯" }, { key: "energy", label: "耗电", unit: "kWh", type: "number" }, { key: "status_at_cutoff", label: "状态" }], rows: [row("L-0348-A", false), row("L-0912-A", true)], row_count: 2, complete: true, chart: null, actions: [{ id: "upstream-1", label: "查询上游 RTU", row_id: "L-0348-A", intent: "inspect_rtu", energy_view: null }], report: [{ title: "一、总体结论", content: "合成固定报告正文" }] };
}

beforeEach(() => { root = fixture(); replayed = false; vi.clearAllMocks(); trigger.mockResolvedValue(undefined); });

describe("照明宿主视图", () => {
  it("RTU 运行筛选使用表格的运行状态,不混用同一行的报警解除状态", () => {
    root.scene = "rtu";
    root.columns = [{ key: "rtu_id", label: "RTU" }, { key: "status", label: "判定时点状态" }];
    root.rows[0].values.status = "上报过期";
    root.rows[1].values.status = "窗口无记录";
    render(<LightingArtefactTab surfaceId="lighting:q1" sessionId="s1" skillId="root-agent" />);
    expect(screen.queryByRole("option", { name: "截止时点未解除" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("筛选状态"), { target: { value: "窗口无记录" } });
    expect(screen.getAllByTestId("lighting-row")).toHaveLength(1);
    expect(screen.getByTestId("lighting-row")).toHaveTextContent("窗口无记录");
    expect(trigger).not.toHaveBeenCalled();
  });
  it("筛选当前清单,保留范围指标、来源时点与缺失值", () => {
    render(<LightingArtefactTab surfaceId="lighting:q1" sessionId="s1" skillId="root-agent" />);
    expect(screen.getByTestId("lighting-provenance")).toHaveTextContent("Asia/Shanghai");
    expect(screen.getByText("缺少生产在线判定配置")).toBeVisible();
    fireEvent.change(screen.getByLabelText("筛选状态"), { target: { value: "截止时点未解除" } });
    expect(screen.getAllByTestId("lighting-row")).toHaveLength(1);
    expect(screen.getByTestId("lighting-metrics")).toHaveTextContent("2 条");
    expect(screen.getByText("0 kWh")).toBeVisible();
    fireEvent.change(screen.getByLabelText("搜索清单"), { target: { value: "does-not-exist" } });
    expect(screen.getByText("当前清单没有匹配记录。")).toBeVisible();
    expect(trigger).not.toHaveBeenCalled();
  });
  it("证据抽屉只传动作编号,同步防重并在失败后允许显式重试", async () => {
    let reject!: (error: Error) => void;
    trigger.mockImplementationOnce(() => new Promise((_resolve, rejectFn) => { reject = rejectFn; }));
    render(<LightingArtefactTab surfaceId="lighting:q1" sessionId="s1" skillId="root-agent" />);
    fireEvent.click(screen.getByRole("button", { name: "查看 L-0348-A 证据" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("alarm-L-0348-A");
    expect(screen.getByRole("dialog")).toHaveTextContent("历史证据窗");
    const action = screen.getByRole("button", { name: "查询上游 RTU" });
    fireEvent.click(action); fireEvent.click(action);
    expect(trigger).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveBeenCalledWith("lighting:q1", { name: "run:lighting.query", context: { actionId: "upstream-1" } });
    reject(new Error("数据源不可用"));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("数据源不可用"));
    fireEvent.click(screen.getByRole("button", { name: "关闭证据抽屉" }));
    fireEvent.click(screen.getByRole("button", { name: "重试本次查询" }));
    await waitFor(() => expect(trigger).toHaveBeenCalledTimes(2));
  });
  it("历史恢复只读,不会自动重放查询;参数仅进入草稿", () => {
    replayed = true;
    const draft = vi.fn();
    render(<LightingArtefactTab surfaceId="lighting:q1" sessionId="s1" skillId="root-agent" onDraftMessage={draft} />);
    expect(screen.getByText(/刷新未重放查询/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "查看 L-0348-A 证据" }));
    expect(screen.getByRole("button", { name: "查询上游 RTU" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "关闭证据抽屉" }));
    fireEvent.click(screen.getByRole("button", { name: "调整查询参数" }));
    fireEvent.change(screen.getByLabelText("设备范围"), { target: { value: "RTU-017" } });
    fireEvent.click(screen.getByRole("button", { name: "放入消息草稿" }));
    expect(draft).toHaveBeenCalledWith(expect.stringContaining("RTU-017"));
    expect(draft).toHaveBeenCalledWith(expect.stringContaining("Asia/Shanghai"));
    expect(trigger).not.toHaveBeenCalled();
  });
  it("查询失败不显示成功指标或空清单", () => {
    root.status = "error"; root.error = "历史来源读取失败";
    render(<LightingArtefactTab surfaceId="lighting:q1" sessionId="s1" skillId="root-agent" />);
    expect(screen.getByRole("alert")).toHaveTextContent("历史来源读取失败");
    expect(screen.queryByTestId("lighting-metrics")).not.toBeInTheDocument();
    expect(screen.queryByText("当前清单没有匹配记录。")).not.toBeInTheDocument();
  });
  it("CSV 保留零和空值,防止文本公式执行", () => {
    expect(rowsToCsv([{ key: "device", label: "设备" }, { key: "energy", label: "kWh" }], [{ device: "=SUM(1)", energy: 0 }, { device: "L-2", energy: null }])).toBe("设备,kWh\r\n'=SUM(1),0\r\nL-2,");
  });
});
