import type { ColumnDecl } from "@/components/workspace/SeriesArtefactTab";

export interface LightingAction {
  id: string;
  label: string;
  intent: string;
  row_id: string | null;
  energy_view: string | null;
}

export interface LightingRow {
  id: string;
  lamp_id: string | null;
  rtu_id: string | null;
  circuit_id: string | null;
  pole_id: string | null;
  alarm_id: string | null;
  phase: string | null;
  anchor: string | null;
  evidence_window: { start: string; end: string } | null;
  relationship_verified: boolean;
  values: Record<string, string | number | boolean | null>;
  evidence: { label: string; value: string | number | boolean | null; unit: string; at: string | null; source: string; note: string }[];
  missing: string[];
}

export interface LightingRoot {
  kind: "lighting";
  title: string;
  scene: string;
  status: "success" | "partial" | "empty" | "error";
  error: string | null;
  summary: string;
  energy_view: string | null;
  query?: {
    id: string;
    scope: string;
    timezone: string;
    window: { start: string; end: string };
    rtu_energy_window: { start: string; end: string } | null;
    cutoff: string;
    generated_at: string;
    basis: string;
    source: string;
    coverage: string;
    filters: string[];
    missing: string[];
  };
  metrics: { label: string; value: string | number | boolean | null; unit: string; note: string }[];
  columns: ColumnDecl[];
  rows: LightingRow[];
  row_count: number;
  complete: boolean;
  chart: { title: string; x_key: string; x_label: string; y: ColumnDecl[]; rows: Record<string, unknown>[]; filter_key: string | null } | null;
  actions: LightingAction[];
  report: { title: string; content: string }[];
}

export function lightingValue(value: unknown, unit = ""): string {
  if (value == null || (typeof value === "number" && !Number.isFinite(value))) return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") {
    if (unit === "ratio") return `${(value * 100).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}%`;
    return `${value.toLocaleString("zh-CN", { maximumFractionDigits: 3 })}${unit ? ` ${unit}` : ""}`;
  }
  return String(value);
}

export function lightingTime(value: string | null | undefined, timezone = "Asia/Shanghai"): string {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}
