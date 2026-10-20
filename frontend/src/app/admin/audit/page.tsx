// Audit trail — who changed what, and when (v6.16.0 Phase 4).
//
// The trail has been written since v6.9.0 and readable by nobody: records piled
// up in `admin_audit` and were reachable only via raw Firestore. This is the
//
// Lives under the "Activity & audit" area of the console IA.

"use client";

import { useCallback, useEffect, useState } from "react";

import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { fetchWithAuth } from "@/lib/apiClient";
import { useConsoleCopy } from "@/components/admin/ConsolePrimitives";

interface AuditEntry {
  id: string;
  ts: string;
  actorUid: string;
  actorEmail: string;
  action: string;
  target: string;
  before?: unknown;
  after?: unknown;
}

interface AuditResponse {
  entries: AuditEntry[];
  scanned: number;
  scope: string;
}

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: AuditResponse };

function fmt(ts: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

export default function AuditPage() {
  const t = useConsoleCopy();
  const { user, loading } = useAuth();
  const { state: scopeState, isAdmin } = useAdminScope(!loading && !!user);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const r = await fetchWithAuth("/api/proxy/api/admin/audit?limit=200");
      if (!r.ok) {
        setState({
          kind: "error",
          message:
            r.status === 403
              ? t("你没有查看审计记录的权限。", "You don't have access to the audit trail.")
              : t(`无法加载审计记录（HTTP ${r.status}）。`, `Couldn't load the audit trail (HTTP ${r.status}).`),
        });
        return;
      }
      setState({ kind: "ready", data: (await r.json()) as AuditResponse });
    } catch {
      setState({ kind: "error", message: t("无法连接管理服务，请检查网络连接。", "Couldn't reach the admin service — this is a connection problem.") });
    }
  }, [t]);

  useEffect(() => {
    if (isAdmin) void load();
  }, [isAdmin, load]);

  if (loading || scopeState === "loading") return <Centered><p role="status" className="skeleton w-full max-w-md p-6 text-center text-sm">{t("正在读取管理权限…", "Loading…")}</p></Centered>;
  if (!user) return <SignInRequired />;
  if (scopeState === "error") {
    return (
      <Centered>
        <p role="alert" className="notice notice--danger">
          {t("无法检查访问权限。这是连接问题，并非权限不足。", "Couldn't check your access. This is a connection problem, not a permissions one.")}
        </p>
      </Centered>
    );
  }
  if (!isAdmin) {
    return (
      <Centered>
        <p className="notice notice--warning">{t("查看审计记录需要管理员权限。", "The audit trail requires an admin group.")}</p>
      </Centered>
    );
  }

  return (
    <main className="page-container mx-auto max-w-5xl">
      <header className="page-header">
        <div className="min-w-0">
          <h1 className="page-header__title">{t("审计记录", "Audit trail")}</h1>
          <p className="page-header__desc">{t("追溯管理变更的操作人、操作内容与发生时间。", "Every admin change: who, what, when.")}</p>
        </div>
      </header>

      <div className="page-body space-y-4">
        {state.kind === "loading" && <p role="status" className="skeleton p-6 text-sm text-muted-foreground">{t("正在加载审计记录…", "Loading…")}</p>}

        {state.kind === "error" && (
          <div role="alert" className="notice notice--danger flex-col">
            <p>{state.message}</p>
            <button className="button-secondary px-3 py-1.5 text-sm" onClick={() => void load()}>
              {t("重试", "Retry")}
            </button>
          </div>
        )}

        {state.kind === "ready" && (
          <section className="glass-panel min-w-0 overflow-hidden">
            {state.data.entries.length === 0 ? (
              <div className="empty-state">
                <h2 className="empty-state__title">{t("暂无审计记录", "No audit entries")}</h2>
                <p className="empty-state__desc">{t("尚未记录任何管理变更。", "No admin changes have been recorded yet.")}</p>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
                  <h2 className="text-sm font-semibold">{t("管理变更", "Admin changes")}</h2>
                  <span className="badge badge--brand">{t(`共 ${state.data.entries.length} 条`, `Showing ${state.data.entries.length}`)}</span>
                </div>
                <div className="max-h-[75vh] overflow-auto">
                  <table className="data-table min-w-[760px]">
                    <thead>
                      <tr>
                        <th>{t("时间", "When")}</th>
                        <th>{t("操作人", "Who")}</th>
                        <th>{t("操作", "Action")}</th>
                        <th>{t("目标", "Target")}</th>
                        <th><span className="sr-only">{t("变更详情", "Change details")}</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.data.entries.map((e) => (
                        <tr key={e.id}>
                          <td className="whitespace-nowrap text-xs text-muted-foreground">{fmt(e.ts)}</td>
                          <td className="max-w-64 break-words text-xs">{e.actorEmail || e.actorUid || "—"}</td>
                          <td>
                            <code className="badge badge--brand">{e.action}</code>
                          </td>
                          <td className="max-w-64 break-words text-xs">{e.target || "—"}</td>
                          <td className="text-right">
                            {(e.before !== null || e.after !== null) && (
                              <button
                                className="button-secondary whitespace-nowrap px-2 py-1 text-xs"
                                aria-expanded={expanded === e.id}
                                onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                              >
                                {expanded === e.id ? t("收起", "Hide") : t("查看变更", "Diff")}
                              </button>
                            )}
                            {expanded === e.id && (
                              <pre className="mt-2 max-h-64 w-80 max-w-full overflow-auto whitespace-pre rounded-md border bg-muted/20 p-3 text-left text-[11px]">
                                {JSON.stringify({ before: e.before, after: e.after }, null, 2)}
                              </pre>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </main>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="page-container flex min-h-screen items-center justify-center p-8">{children}</main>;
}
