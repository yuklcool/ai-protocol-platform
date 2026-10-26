"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useSurfaceRegistry, useSurfaceState } from "@/providers/SurfaceRegistry";
import { useActionDrivenAgent } from "@/hooks/useActionDrivenAgent";
import { lightingTime, lightingValue, type LightingAction, type LightingRoot, type LightingRow } from "@/lib/lighting";
import { compareRows, rowsToCsv, SeriesView, type ColumnDecl } from "./SeriesArtefactTab";

/** All lighting skills share this host view; only trusted result data varies. */
export function LightingArtefactTab({ surfaceId, sessionId, skillId, onDraftMessage, busy = false }: { surfaceId: string; sessionId: string | null; skillId: string; onDraftMessage?: (text: string) => void; busy?: boolean }) {
  const state = useSurfaceState(surfaceId);
  const root = state?.surface?.dataModel?.get("/") as LightingRoot | undefined;
  const registry = useSurfaceRegistry();
  const mount = useRef<HTMLDivElement>(null);
  const drawerOpener = useRef<HTMLElement | null>(null);
  const drafted = useRef(false);
  useLayoutEffect(() => { registry.register(surfaceId, mount); return () => registry.unregister(surfaceId); }, [registry, surfaceId]);
  const { triggerAction, cancelAction } = useActionDrivenAgent({ sessionId: sessionId ?? "", skillId });
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [point, setPoint] = useState<unknown>(null);
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" } | null>(null);
  const [page, setPage] = useState(0);
  const [drawer, setDrawer] = useState<"report" | "parameters" | string | null>(null);
  const [running, setRunning] = useState(false);
  const runningRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<LightingAction | null>(null);
  const [done, setDone] = useState(false);
  const query = root?.query;
  const timezone = query?.timezone ?? "Asia/Shanghai";
  const statusKey = root?.scene === "rtu" || root?.scene === "reconcile" ? "status" : "status_at_cutoff";
  useEffect(() => {
    setSearch(""); setPoint(null); setPage(0); setDrawer(null);
    setFilter(root?.scene === "lamp_alarms" && root.rows.some(row => row.values.status_at_cutoff === "截止时点未解除") ? "截止时点未解除" : "all");
    setSort(root?.scene === "reconcile" ? { key: "difference_kwh", dir: "desc" } : null);
  }, [query?.id, root?.scene]);
  const rows = useMemo(() => {
    const selected = (root?.rows ?? []).filter(row => {
      const values = { ...row.values, id: row.id, lamp_id: row.lamp_id, rtu_id: row.rtu_id, circuit_id: row.circuit_id, alarm_id: row.alarm_id };
      if (search && !Object.values(values).some(value => value != null && String(value).toLocaleLowerCase().includes(search.toLocaleLowerCase()))) return false;
      if (filter !== "all" && String(row.values[statusKey] ?? "证据不足") !== filter) return false;
      if (point !== null && root?.chart?.filter_key && row.values[root.chart.filter_key] !== point) return false;
      return true;
    });
    if (!sort) return selected;
    const column = root?.columns?.find(col => col.key === sort.key);
    const flat = (row: LightingRow) => ({ ...row.values, id: row.id, lamp_id: row.lamp_id, rtu_id: row.rtu_id, circuit_id: row.circuit_id, alarm_id: row.alarm_id });
    return [...selected].sort((a, b) => compareRows(flat(a), flat(b), sort.key, column?.type, sort.dir));
  }, [root, search, filter, point, sort, statusKey]);
  const statuses = Array.from(new Set((root?.rows ?? []).map(row => String(row.values[statusKey] ?? "证据不足"))));
  const selectedRow = drawer?.startsWith("row:") ? root?.rows?.find(row => row.id === drawer.slice(4)) : undefined;
  const readOnly = Boolean(state?.artifact?.replayed);
  const disabled = running || busy || readOnly || !sessionId;
  function openDrawer(value: string) {
    drawerOpener.current = document.activeElement as HTMLElement | null;
    drafted.current = false;
    setDrawer(value);
  }
  async function run(action: LightingAction) {
    if (runningRef.current || disabled) return;
    runningRef.current = true; setRunning(true); setError(null); setDone(false); setLastAction(action);
    try {
      await triggerAction(surfaceId, { name: "run:lighting.query", context: { actionId: action.id } });
      setDone(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "查询失败,请核对后重试。"); }
    finally { runningRef.current = false; setRunning(false); }
  }
  function download() {
    if (!root || root.status === "error" || rows.length === 0) return;
    const flat = rows.map(row => ({ ...row.values, id: row.id, lamp_id: row.lamp_id, rtu_id: row.rtu_id, circuit_id: row.circuit_id, alarm_id: row.alarm_id }));
    const url = URL.createObjectURL(new Blob(["\uFEFF", rowsToCsv(root.columns, flat)], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `lighting-${query?.id ?? "query"}-current-list.csv`; link.click(); URL.revokeObjectURL(url);
  }
  function cell(row: LightingRow, column: ColumnDecl) {
    const value = ({ ...row.values, id: row.id, lamp_id: row.lamp_id, rtu_id: row.rtu_id, circuit_id: row.circuit_id, alarm_id: row.alarm_id } as Record<string, unknown>)[column.key];
    if (column.key === "status_at_cutoff" || column.key === "status") {
      const label = lightingValue(value);
      const tone = label.includes("未解除") || label === "倒挂" ? "bg-amber-50 text-amber-800" : label.includes("已解除") ? "bg-emerald-50 text-emerald-800" : "bg-muted text-muted-foreground";
      return <span className={`rounded-md px-2 py-1 text-xs ${tone}`}>{label}</span>;
    }
    return column.type === "time" ? lightingTime(value as string | null, timezone) : lightingValue(value, column.unit);
  }
  const actionButton = (action: LightingAction) => <button key={action.id} type="button" className="button-secondary min-h-11 text-xs" disabled={disabled} onClick={() => void run(action)}>{action.label}</button>;
  return <div ref={mount} data-testid="lighting-result" data-scene={root?.scene} className="h-full min-w-0 overflow-auto bg-background p-4 text-sm sm:p-6" aria-busy={running}>
    {!root ? <p role="status">正在读取照明结果…</p> : <div className="mx-auto grid max-w-6xl gap-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><p className="text-xs text-muted-foreground">照明查询{readOnly ? " · 历史结果" : ""}</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">{root.title}</h2></div>
        <div className="flex flex-wrap gap-2">{onDraftMessage && <button type="button" className="button-secondary min-h-11 text-xs md:hidden" onClick={() => onDraftMessage("")}>继续提问</button>}<button type="button" className="button-secondary min-h-11 text-xs" onClick={() => openDrawer("parameters")} disabled={!query}>调整查询参数</button><button type="button" className="button-secondary min-h-11 text-xs" onClick={() => openDrawer("report")} disabled={!root.report?.length || root.status === "error"}>完整报告</button></div>
      </header>
      {query && <div className="grid gap-1 break-words text-xs leading-6 text-muted-foreground" data-testid="lighting-provenance">
        <p>{query.scope} · {lightingTime(query.window.start, timezone)} → {lightingTime(query.window.end, timezone)} · {timezone} · {query.basis === "daily" ? "自然日 D 日报" : query.basis === "night" ? "跨日夜间窗口" : "历史证据窗口"}</p>
        <p>数据截止 {lightingTime(query.cutoff, timezone)} · 生成 {lightingTime(query.generated_at, timezone)} · 来源 {query.source}</p>
        <p>{query.coverage}</p>
        {query.rtu_energy_window && <p>RTU 夜间能耗另用 {lightingTime(query.rtu_energy_window.start, timezone)} → {lightingTime(query.rtu_energy_window.end, timezone)}</p>}
      </div>}
      {readOnly && <p className="notice text-xs">这是原查询时点的结果,刷新未重放查询。需要新数据时可调整参数并放入消息草稿。</p>}
      {root.status === "error" ? <p role="alert" className="notice border-destructive/30 text-destructive">{root.error || "查询失败,不能据此判断正常或零报警。"}</p> : <>
        <p className="rounded-xl border bg-white px-4 py-3 leading-7">{root.summary}</p>
        {root.status === "empty" && <p role="status" className="notice">当前范围没有记录。无记录与无异常分开判断。</p>}
        {root.status === "partial" && <div className="notice grid gap-1" role="status"><strong className="font-medium">部分证据缺失,相关判断暂不能定性。</strong>{query?.missing.map((item, index) => <p key={index}>{item}</p>)}</div>}
        {!!root.metrics?.length && <dl className="grid grid-cols-2 divide-x divide-y overflow-hidden rounded-xl border bg-white lg:grid-cols-4" data-testid="lighting-metrics">{root.metrics.map((metric, index) => <div key={index} className="min-w-0 px-4 py-3"><dt className="text-xs text-muted-foreground">{metric.label}</dt><dd className="my-1 break-words text-2xl font-semibold tabular-nums">{lightingValue(metric.value, metric.unit)}</dd><dd className="text-xs leading-5 text-muted-foreground">{metric.note}</dd></div>)}</dl>}
      </>}
      <div className="flex flex-wrap gap-2" aria-label="继续查询">{root.actions?.filter(action => !action.row_id).map(action => <button key={action.id} type="button" className="button-secondary min-h-11 text-xs" disabled={disabled} aria-pressed={action.energy_view ? root.energy_view === action.energy_view : undefined} onClick={() => void run(action)}>{action.energy_view ? `查询${action.label}` : action.label}</button>)}</div>
      {running && <div role="status" className="notice flex items-center justify-between gap-2"><span>正在读取照明证据,请稍候…</span><button type="button" className="button-secondary min-h-11" onClick={cancelAction}>停止查询</button></div>}
      {error && <div role="alert" className="notice grid gap-2 text-destructive"><p>{error}</p>{lastAction && <button type="button" className="button-secondary w-fit min-h-11" disabled={disabled} onClick={() => void run(lastAction)}>重试本次查询</button>}</div>}
      {done && !running && <p role="status" className="text-xs text-muted-foreground">本次查询响应已返回,请查看新增结果与结论。</p>}
      {root.status !== "error" && root.chart && <section className="min-w-0 overflow-hidden rounded-xl border bg-white"><h3 className="px-4 pt-4 font-medium">{root.chart.title}</h3><SeriesView compact root={{ kind: "series", title: root.chart.title, x: { key: root.chart.x_key, label: root.chart.x_label, type: "category" }, y: root.chart.y, rows: root.chart.rows }} onSelectRow={root.chart.filter_key ? row => { setPoint(row[root.chart!.x_key]); setPage(0); } : undefined} />{point !== null && <button type="button" className="button-ghost m-2 min-h-11 text-xs" onClick={() => setPoint(null)}>清除图表筛选：{String(point)}</button>}</section>}
      {root.status !== "error" && <section className="min-w-0 overflow-hidden rounded-xl border bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 p-4"><h3 className="font-medium">{root.scene === "reconcile" ? "D 日报对账清单" : "查询清单"}</h3><button type="button" className="button-secondary min-h-11 text-xs" disabled={!rows.length} onClick={download}>下载当前清单 CSV</button></div>
        <div className="flex flex-wrap gap-2 px-4 pb-3"><label className="min-w-0 flex-1"><span className="sr-only">搜索清单</span><input className="glass-control min-h-11 w-full px-3 text-base sm:text-sm" value={search} onChange={event => { setSearch(event.target.value); setPage(0); }} placeholder="搜索单灯、道路、RTU、回路" /></label><label><span className="sr-only">筛选状态</span><select className="glass-control min-h-11 max-w-full px-2" value={filter} onChange={event => { setFilter(event.target.value); setPage(0); }}><option value="all">全部状态</option>{statuses.map(status => <option key={status}>{status}</option>)}</select></label></div>
        <div className="max-h-[28rem] max-w-full overflow-auto overscroll-contain" tabIndex={0} role="region" aria-label="照明查询表格"><table className="w-full border-collapse whitespace-nowrap text-xs"><thead className="sticky top-0 bg-[#FAFAFB]"><tr>{root.columns?.map(col => <th key={col.key} scope="col" aria-sort={sort?.key === col.key ? sort.dir === "asc" ? "ascending" : "descending" : "none"} className="border-b px-3 text-left font-normal text-muted-foreground"><button className="min-h-11" type="button" onClick={() => { setSort({ key: col.key, dir: sort?.key === col.key && sort.dir === "asc" ? "desc" : "asc" }); setPage(0); }}>{col.label}{col.unit && col.unit !== "ratio" ? ` (${col.unit})` : ""}{sort?.key === col.key ? sort.dir === "asc" ? " ↑" : " ↓" : ""}</button></th>)}<th scope="col" className="px-3 font-normal">证据</th></tr></thead><tbody>{rows.slice(page * 100, page * 100 + 100).map(row => <tr key={row.id} className="border-b last:border-0 hover:bg-muted/20" data-testid="lighting-row">{root.columns.map(col => <td key={col.key} className={`px-3 py-2 tabular-nums ${col.type === "number" ? "text-right" : ""}`}>{cell(row, col)}</td>)}<td className="px-3"><button type="button" className="min-h-11 text-primary" onClick={() => openDrawer(`row:${row.id}`)} aria-label={`查看 ${row.lamp_id || row.rtu_id || row.id} 证据`}>查看证据</button></td></tr>)}</tbody></table>{!rows.length && <p role="status" className="p-5 text-muted-foreground">当前清单没有匹配记录。</p>}</div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t px-4 py-2 text-xs text-muted-foreground"><p>当前清单 {rows.length} / 已返回 {root.rows?.length ?? 0} 条 · 查询范围共 {root.row_count} 条。筛选不改写范围汇总。{!root.complete ? " 结果未完整返回。" : ""}</p>{rows.length > 100 && <div className="flex items-center gap-2"><button type="button" className="button-ghost min-h-11" disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1}</span><button type="button" className="button-ghost min-h-11" disabled={(page + 1) * 100 >= rows.length} onClick={() => setPage(page + 1)}>下一页</button></div>}</div>
      </section>}
      {!!query?.filters.length && <details className="text-xs leading-6 text-muted-foreground"><summary className="min-h-11 cursor-pointer">统计与过滤口径</summary>{query.filters.map((item, index) => <p key={index}>{item}</p>)}</details>}
    </div>}
    <Dialog.Root open={drawer !== null} onOpenChange={open => { if (!open) setDrawer(null); }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/25" /><Dialog.Content onCloseAutoFocus={event => { event.preventDefault(); if (!drafted.current) drawerOpener.current?.focus(); }} className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[650px] flex-col border-l bg-white shadow-xl" aria-describedby="lighting-drawer-description">
      <div className="flex items-center justify-between gap-3 border-b px-5 py-3"><Dialog.Title className="break-words text-lg font-semibold">{drawer === "report" ? "完整固定格式报告" : drawer === "parameters" ? "准备下一次查询" : selectedRow?.lamp_id || selectedRow?.rtu_id || "设备证据"}</Dialog.Title><Dialog.Close className="button-ghost h-11 w-11 shrink-0" aria-label="关闭证据抽屉"><X className="h-5 w-5" /></Dialog.Close></div>
      <div className="grid min-h-0 gap-5 overflow-auto p-5 text-sm"><Dialog.Description id="lighting-drawer-description" className="text-xs leading-6 text-muted-foreground">{drawer === "parameters" ? "参数放入消息草稿后由你检查并发送,此操作不会读取远端数据。" : `依据原查询时点与来源查看证据 · ${timezone}`}</Dialog.Description>
        {drawer === "report" && root?.report?.map((section, index) => <section className="border-b pb-4 last:border-0" key={index}><h3 className="mb-2 font-medium">{section.title}</h3><p className="whitespace-pre-wrap break-words leading-7">{section.content}</p></section>)}
        {drawer === "parameters" && query && <QueryParameters query={query} title={root?.title ?? "照明运行"} onDraft={text => { drafted.current = true; onDraftMessage?.(text); setDrawer(null); }} available={Boolean(onDraftMessage)} />}
        {selectedRow && <>
          <dl className="grid grid-cols-[100px_minmax(0,1fr)] gap-x-3 gap-y-2 break-words text-xs">{[["单灯", selectedRow.lamp_id], ["灯杆", selectedRow.pole_id], ["RTU / 回路", [selectedRow.rtu_id, selectedRow.circuit_id].filter(Boolean).join(" / ")], ["报警事件", selectedRow.alarm_id], ["相位 / 支路", selectedRow.phase], ["时间锚点", lightingTime(selectedRow.anchor, timezone)], ["归属证据", selectedRow.relationship_verified ? "已取得" : "尚未取得"]].map(([label, value]) => <div key={label} className="contents"><dt className="text-muted-foreground">{label}</dt><dd>{value || "—"}</dd></div>)}</dl>
          {selectedRow.evidence_window && <p className="text-xs text-muted-foreground">历史证据窗：{lightingTime(selectedRow.evidence_window.start, timezone)} → {lightingTime(selectedRow.evidence_window.end, timezone)}</p>}
          <section><h3 className="mb-2 font-medium">历史读数与专项证据</h3>{selectedRow.evidence.length ? <div className="divide-y rounded-xl border">{selectedRow.evidence.map((item, index) => <div className="grid gap-1 px-4 py-3" key={index}><div className="flex flex-wrap justify-between gap-2"><span>{item.label}</span><strong className="font-medium tabular-nums">{lightingValue(item.value, item.unit)}</strong></div><p className="break-words text-xs text-muted-foreground">{lightingTime(item.at, timezone)} · {item.source}{item.note ? ` · ${item.note}` : ""}</p></div>)}</div> : <p className="notice">尚未取得该设备的历史证据,不能用当前末态反推历史。</p>}</section>
          {!!selectedRow.missing.length && <section className="notice grid gap-2"><h3 className="font-medium">证据缺口</h3>{selectedRow.missing.map((item, index) => <p key={index}>{item}</p>)}</section>}
          {root?.scene === "rtu_alarms" && <p className="notice text-xs leading-6">专项核查：漏电 ≤1 A 不能认定安全;缺相需同时核对电流与回路;过流缺额定值不算超出比例;断路先确认灯型。没有动作记录不能认定动作失败。</p>}
          {root?.scene === "rtu_alarms" && <SpecializedEvidence row={selectedRow} onDraft={onDraftMessage ? kind => { drafted.current = true; onDraftMessage(`补充报警 ${selectedRow.alarm_id} 的灯具类型为${kind},查询 ${selectedRow.rtu_id} / 回路 ${selectedRow.circuit_id}。原查询 ${query?.id},时间锚点 ${selectedRow.anchor},证据窗 ${selectedRow.evidence_window?.start} 至 ${selectedRow.evidence_window?.end}（${timezone}）。请沿用原专项技能只读核查。`); setDrawer(null); } : undefined} />}
          {running && <div role="status" className="notice flex items-center justify-between gap-2"><span>正在读取照明证据,请稍候…</span><button type="button" className="button-secondary min-h-11" onClick={cancelAction}>停止查询</button></div>}
          {error && <div role="alert" className="notice grid gap-2 text-destructive"><p>{error}</p>{lastAction && <button type="button" className="button-secondary min-h-11" disabled={disabled} onClick={() => void run(lastAction)}>重试本次查询</button>}</div>}
          {done && !running && !error && <p role="status" className="text-xs text-muted-foreground">本次查询响应已返回,关闭抽屉可查看新增结果。</p>}
          <div className="flex flex-wrap gap-2 border-t pt-4">{root?.actions.filter(action => action.row_id === selectedRow.id).map(actionButton)}</div>
        </>}
      </div>
    </Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>;
}

const SPECIALIZED_FIELDS: Record<string, [string, string][]> = {
  "漏电": [["leakage_unit", "原始单位"], ["trip_record", "自动断电记录"], ["lockout", "闭锁保护"], ["post_trip_samples", "断电后有效采样"]],
  "缺相": [["day_night", "昼夜"], ["phase_mapping", "相位与回路对应"], ["phase_current", "同事件相电流"], ["circuit_current", "回路电流"], ["related_break_alarm", "关联断路报警"]],
  "过流": [["previous_two_days", "前两日同时段曲线"], ["curve_rule", "曲线一致性标准"], ["rated_current", "回路额定电流 (A)"], ["actual_current", "实际电流 (A)"], ["above_rated_rate", "高于额定比例"]],
  "断路": [["lamp_kind", "灯具类型"], ["continuous_current", "连续回路电流"], ["pre_alarm_current", "报警前电流"], ["total_current", "对应总电流"]],
};

function SpecializedEvidence({ row, onDraft }: { row: LightingRow; onDraft?: (kind: string) => void }) {
  const kind = String(row.values.alarm_type ?? "");
  const [lampKind, setLampKind] = useState("道路灯");
  const fields = SPECIALIZED_FIELDS[kind];
  if (!fields) return null;
  return <section className="grid gap-3"><h3 className="font-medium">{kind}专项证据</h3><dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3 text-xs">{fields.map(([key, label]) => <div key={key} className="contents"><dt className="text-muted-foreground">{label}</dt><dd className="break-words">{lightingValue(row.values[key], key === "above_rated_rate" ? "ratio" : "")}</dd></div>)}</dl>{kind === "断路" && row.values.lamp_kind == null && <div className="grid gap-2"><label className="grid gap-2 text-xs">补充灯具类型<select className="glass-control min-h-11 px-3 text-base" value={lampKind} onChange={event => setLampKind(event.target.value)}><option>道路灯</option><option>亮化灯</option></select></label><p className="text-xs leading-6 text-muted-foreground">亮化灯路径结束不能据此认定正常;道路灯继续核对连续电流与报警前电流。</p><button type="button" className="button-secondary min-h-11" disabled={!onDraft} onClick={() => onDraft?.(lampKind)}>将补充参数放入消息草稿</button></div>}</section>;
}

function QueryParameters({ query, title, onDraft, available }: { query: NonNullable<LightingRoot["query"]>; title: string; onDraft: (text: string) => void; available: boolean }) {
  const [scope, setScope] = useState(query.scope);
  const local = (value: string) => {
    const parts = new Intl.DateTimeFormat("sv-SE", { timeZone: query.timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(value));
    return parts.replace(" ", "T");
  };
  const [start, setStart] = useState(local(query.window.start));
  const [end, setEnd] = useState(local(query.window.end));
  const [error, setError] = useState("");
  return <form className="grid gap-4" onSubmit={event => { event.preventDefault(); if (end <= start) { setError("结束时间必须晚于开始时间。"); return; } if (query.basis === "daily" && (start.slice(11) !== "00:00" || end.slice(11) !== "00:00")) { setError("D 日报须使用自然日 00:00 边界。"); return; } onDraft(`查询${scope}的${title},时间为 ${start.replace("T", " ")} 至 ${end.replace("T", " ")}（${query.timezone}）,采用${query.basis === "daily" ? "自然日 D 日报" : "原查询时间口径"}。原查询编号 ${query.id}。`); }}>
    <label className="grid gap-2 text-xs">设备范围<input className="glass-control min-h-11 px-3 text-base" required maxLength={200} value={scope} onChange={event => setScope(event.target.value)} /></label>
    <label className="grid gap-2 text-xs">开始时间（{query.timezone}）<input type="datetime-local" required className="glass-control min-h-11 min-w-0 max-w-full px-3 text-base" value={start} onChange={event => setStart(event.target.value)} /></label>
    <label className="grid gap-2 text-xs">结束时间（{query.timezone}）<input type="datetime-local" required className="glass-control min-h-11 min-w-0 max-w-full px-3 text-base" value={end} onChange={event => setEnd(event.target.value)} /></label>
    {error && <p role="alert" className="text-destructive">{error}</p>}
    <button type="submit" className="button-primary min-h-11" disabled={!available}>放入消息草稿</button>
  </form>;
}
