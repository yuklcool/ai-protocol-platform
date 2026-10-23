"use client";

import { useEffect, useId, useState } from "react";
import { FileText, Download, Save, X } from "lucide-react";
import { fetchWithAuth } from "@/lib/apiClient";
import { useI18n } from "@/contexts/I18nContext";

export type SavedReport = { report_id: string; message_id: string; title: string; content: string; revision: number; updated_at: string };

export function ReportEditor({ sessionId, messageId, content, initialReport }: { sessionId: string; messageId: string; content: string; initialReport?: SavedReport }) {
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const id = useId();
  const [open, setOpen] = useState(false);
  const [report, setReport] = useState<SavedReport | undefined>(initialReport);
  const [draft, setDraft] = useState(content);
  const [title, setTitle] = useState(zh ? "任务报告" : "Task report");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const hasChanges = loaded && (draft !== (report?.content ?? content) || title !== (report?.title ?? (zh ? "任务报告" : "Task report")));
  const endpoint = `/api/proxy/api/sessions/${encodeURIComponent(sessionId)}/reports`;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setBusy(true); setLoaded(false); setError("");
    void fetchWithAuth(endpoint, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json() as { reports: SavedReport[] };
      if (controller.signal.aborted) return;
      const current = data.reports.find(row => row.message_id === messageId);
      setReport(current); setDraft(current?.content ?? content); setTitle(current?.title ?? (zh ? "任务报告" : "Task report")); setLoaded(true);
    }).catch(() => { if (!controller.signal.aborted) setError(zh ? "无法读取已保存版本，请关闭后重试。" : "Could not load saved version. Close and retry."); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [open, endpoint, messageId, content, zh]);
  const save = async () => {
    setBusy(true); setError(""); setSaved(false);
    try {
      const response = await fetchWithAuth(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message_id: messageId, title: title.trim(), content: draft, expected_revision: report?.revision ?? 0 }) });
      if (!response.ok) throw new Error(response.status === 409 ? (zh ? "报告已在其他窗口更新。请复制当前草稿，关闭后重新打开，再合并保存。" : "Report changed in another window. Copy your draft, reopen and merge before saving.") : (zh ? "保存失败，请核对会话所有权和网络后重试。" : "Save failed. Check session ownership and connection."));
      setReport(await response.json() as SavedReport); setSaved(true);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };
  const download = async () => {
    if (!report) return;
    setBusy(true); setError("");
    try {
      const response = await fetchWithAuth(`${endpoint}/${encodeURIComponent(report.report_id)}/download`);
      if (!response.ok) throw new Error();
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${report.title.replace(/[<>:"/\\|?*]/g, "_")}.txt`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError(zh ? "下载失败，请重试。" : "Download failed. Retry."); }
    finally { setBusy(false); }
  };
  if (!open) return <button type="button" className="button-ghost text-xs" onClick={() => setOpen(true)}><FileText className="h-4 w-4" />{zh ? "编辑并保存报告" : "Edit & save report"}</button>;
  return <section className="report-editor space-y-3" aria-label={zh ? "报告编辑器" : "Report editor"}>
    <header className="flex flex-wrap items-center justify-between gap-2"><h3>{zh ? "任务报告" : "Task report"}</h3><button type="button" className="button-ghost" disabled={busy} onClick={() => { if (!hasChanges || window.confirm(zh ? "关闭后放弃未保存修改？" : "Discard unsaved changes?")) setOpen(false); }} aria-label={zh ? "关闭报告编辑器" : "Close report editor"}><X className="h-4 w-4" /></button></header>
    <label className="block text-xs font-medium" htmlFor={`${id}-title`}>{zh ? "报告名称" : "Report title"}</label>
    <input id={`${id}-title`} className="glass-control w-full px-3" maxLength={200} value={title} disabled={!loaded || busy} onChange={event => { setTitle(event.target.value); setSaved(false); }} />
    <label className="block text-xs font-medium" htmlFor={`${id}-body`}>{zh ? "报告正文" : "Report content"}</label>
    <textarea id={`${id}-body`} className="glass-control min-h-64 w-full p-3" maxLength={200000} value={draft} disabled={!loaded || busy} onChange={event => { setDraft(event.target.value); setSaved(false); }} />
    {error && <p role="alert" className="notice notice--danger">{error}</p>}
    {saved && <p role="status" className="text-sm text-[var(--success)]">{zh ? "报告已保存，可在我的成果中查看。" : "Report saved. Find it in Results."}</p>}
    <footer className="flex flex-wrap items-center gap-2"><button type="button" className="button-primary text-sm" disabled={busy || !loaded || !draft.trim() || !title.trim()} onClick={() => void save()}><Save className="h-4 w-4" />{busy ? (zh ? "处理中…" : "Working…") : (zh ? "保存报告" : "Save report")}</button><button type="button" className="button-secondary text-sm" disabled={busy || !report} onClick={() => void download()}><Download className="h-4 w-4" />{zh ? "下载已保存 TXT" : "Download saved TXT"}</button>{report && <span className="font-mono text-xs text-muted-foreground">v{report.revision}</span>}</footer>
  </section>;
}
