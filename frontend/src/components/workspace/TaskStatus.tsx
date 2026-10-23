"use client";

import { useI18n } from "@/contexts/I18nContext";

export const TASK_STATUS_LABELS: Record<string, [string, string]> = {
  needs_input: ["待确认 / 补充", "Needs input"],
  running: ["执行中", "Running"],
  pending: ["待执行", "Pending"],
  completed: ["已完成", "Completed"],
  failed: ["执行失败", "Failed"],
  cancelled: ["已取消", "Cancelled"],
  unplanned: ["未提供计划", "No reported plan"],
};

export function TaskStatus({ status = "unplanned" }: { status?: string }) {
  const { locale } = useI18n();
  const label = TASK_STATUS_LABELS[status] ?? TASK_STATUS_LABELS.unplanned;
  const tone = status === "completed" ? "success" : status === "failed" ? "danger" : status === "needs_input" ? "warning" : "brand";
  return <span className={`badge badge--${tone}`}><span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />{label[locale.startsWith("zh") ? 0 : 1]}</span>;
}
