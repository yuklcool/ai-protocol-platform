"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { SignInRequired } from "@/components/chat/SignInRequired";
import {
  action,
  consoleApi,
  control,
  errorText,
  Field,
  jsonBody,
  Notice,
  useConsoleCopy,
} from "@/components/admin/ConsolePrimitives";

type PermType = "user" | "domain" | "tenant" | "wildcard";
type Permission = {
  doc_id: string;
  type: PermType;
  tools: string[];
  denied: string[];
  tenantId?: string;
};
export function inferPermissionType(id: string): PermType {
  return id === "*"
    ? "wildcard"
    : id.startsWith("tenant:")
      ? "tenant"
      : id.includes("@")
        ? "user"
        : "domain";
}
const split = (raw: string) => [
  ...new Set(raw.split(/[\s,]+/).filter(Boolean)),
];

export default function ToolPermissionsPage() {
  const { user, loading } = useAuth();
  const t = useConsoleCopy();
  if (loading) return <main className="p-8">{t("加载中…", "Loading…")}</main>;
  if (!user) return <SignInRequired />;
  return <Permissions />;
}
function Permissions() {
  const t = useConsoleCopy();
  const [rows, setRows] = useState<Permission[]>([]);
  const [docId, setDocId] = useState("");
  const [type, setType] = useState<PermType>("tenant");
  const [tools, setTools] = useState("");
  const [denied, setDenied] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try {
      setRows(await consoleApi<Permission[]>("/admin/tool-permissions"));
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const key =
    type === "wildcard"
      ? "*"
      : type === "tenant"
        ? `tenant:${docId.replace(/^tenant:/, "").trim()}`
        : docId.trim();
  const save = async () => {
    setBusy(true);
    setNotice("");
    try {
      await consoleApi(
        `/admin/tool-permissions/${encodeURIComponent(key)}`,
        jsonBody("PUT", { type, tools: split(tools), denied: split(denied) }),
      );
      await load();
      setNotice(
        t("权限已保存并立即刷新。", "Permissions saved; cache refreshed."),
      );
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const labels: Record<PermType, string> = {
    tenant: t("租户", "Tenant"),
    user: t("用户", "User"),
    domain: t("兼容域名", "Legacy domain"),
    wildcard: t("平台默认", "Platform default"),
  };
  return (
    <main className="mx-auto max-w-6xl space-y-5 p-5 sm:p-8">
      <header>
        <h1 className="text-xl font-semibold">
          {t("工具权限", "Tool permissions")}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {t(
            "按用户、稳定租户、兼容域名和平台默认规则计算工具访问权限；禁止项优先。",
            "Tool permissions resolve by user, stable tenant, legacy domain and platform default. Denials take precedence.",
          )}
        </p>
      </header>
      <Notice>{notice}</Notice>
      <section className="overflow-x-auto rounded-lg border">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/40">
            <tr>
              {[
                t("对象", "Target"),
                t("类型", "Type"),
                t("允许", "Allow"),
                t("禁止", "Deny"),
                t("操作", "Actions"),
              ].map((label) => (
                <th key={label} className="p-3 font-medium">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.doc_id} className="border-t">
                <td className="p-3 break-all">{row.doc_id}</td>
                <td className="p-3">{labels[row.type]}</td>
                <td className="p-3">{row.tools.join(", ") || "—"}</td>
                <td className="p-3">{row.denied.join(", ") || "—"}</td>
                <td className="space-x-2 whitespace-nowrap p-3">
                  <button
                    className={action}
                    onClick={() => {
                      setDocId(row.doc_id.replace(/^tenant:/, ""));
                      setType(row.type);
                      setTools(row.tools.join(", "));
                      setDenied(row.denied.join(", "));
                    }}
                  >
                    {t("编辑", "Edit")}
                  </button>
                  <button
                    className={action}
                    disabled={busy}
                    onClick={async () => {
                      if (
                        !window.confirm(
                          t("删除此权限规则？", "Delete this permission rule?"),
                        )
                      )
                        return;
                      setBusy(true);
                      try {
                        await consoleApi(
                          `/admin/tool-permissions/${encodeURIComponent(row.doc_id)}`,
                          { method: "DELETE" },
                        );
                        await load();
                        setNotice(t("规则已删除。", "Rule deleted."));
                      } catch (error) {
                        setNotice(errorText(error));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {t("删除", "Delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading ? (
          <p className="p-4">{t("加载中…", "Loading…")}</p>
        ) : (
          rows.length === 0 && (
            <p className="p-4 text-muted-foreground">
              {t("暂无可见规则。", "No visible rules.")}
            </p>
          )
        )}
      </section>
      <section className="space-y-4 rounded-lg border p-5">
        <h2 className="font-medium">
          {t("新增或更新规则", "Add or update a rule")}
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("规则类型", "Rule type")}>
            <select
              className={control}
              value={type}
              onChange={(e) => {
                const next = e.target.value as PermType;
                setType(next);
                setDocId(next === "wildcard" ? "*" : "");
              }}
            >
              {(Object.keys(labels) as PermType[]).map((value) => (
                <option key={value} value={value}>
                  {labels[value]}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label={
              type === "tenant"
                ? t("稳定租户 ID", "Stable tenant ID")
                : t("目标标识", "Target identifier")
            }
          >
            <input
              className={control}
              value={docId}
              disabled={type === "wildcard"}
              onChange={(e) => setDocId(e.target.value)}
            />
          </Field>
          <Field
            label={t(
              "允许工具（逗号分隔，* 表示全部）",
              "Allowed tools (comma separated; * means all)",
            )}
          >
            <input
              className={control}
              value={tools}
              onChange={(e) => setTools(e.target.value)}
            />
          </Field>
          <Field
            label={t(
              "禁止工具（优先于允许）",
              "Denied tools (override allowed tools)",
            )}
          >
            <input
              className={control}
              value={denied}
              onChange={(e) => setDenied(e.target.value)}
            />
          </Field>
        </div>
        <button
          className={action}
          disabled={busy || (type !== "wildcard" && !docId.trim())}
          onClick={() => void save()}
        >
          {busy ? t("保存中…", "Saving…") : t("保存规则", "Save rule")}
        </button>
      </section>
    </main>
  );
}
