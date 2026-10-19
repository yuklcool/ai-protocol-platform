"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { SignInRequired } from "@/components/chat/SignInRequired";
import {
  ResourceChecklist,
  type ResourceOption,
} from "@/components/admin/ResourceChecklist";
import { TenantRootEditor } from "@/components/admin/TenantRootEditor";
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

type Tenant = {
  tenantId: string;
  displayName: string;
  domains: string[];
  enabledSkills?: string[] | null;
  enabledMcpServers?: string[];
  storageNamespace: string;
  documentsBucket?: string | null;
  disabled: boolean;
  modelPolicy: {
    allowedModels?: string[] | null;
    defaultModel?: string | null;
  };
  quota: {
    llmBudgetUsd?: number;
    llmBudgetPeriod?: string;
    llmBudgetSoftThreshold?: number;
  };
};
type Model = { id: string; label?: string; name?: string };
const blank = (): Tenant => ({
  tenantId: "",
  displayName: "",
  domains: [],
  storageNamespace: "",
  disabled: false,
  modelPolicy: {},
  quota: {},
});
const split = (value: string) => [
  ...new Set(value.split(/[\s,]+/).filter(Boolean)),
];

export default function TenantAdminPage() {
  const { user, loading } = useAuth();
  const t = useConsoleCopy();
  if (loading) return <main className="page-container p-8">{t("加载中…", "Loading…")}</main>;
  if (!user) return <SignInRequired />;
  return <Tenants />;
}
function Tenants() {
  const t = useConsoleCopy();
  const scope = useAdminScope();
  const [rows, setRows] = useState<Tenant[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [draft, setDraft] = useState<Tenant | null>(null);
  const [editing, setEditing] = useState(false);
  const [domainsText, setDomainsText] = useState("");
  const [resources, setResources] = useState<{
    skills: ResourceOption[];
    mcpServers: ResourceOption[];
  }>({ skills: [], mcpServers: [] });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [validation, setValidation] = useState<
    Array<{ field: string; message: string; level: string }>
  >([]);
  const load = useCallback(async () => {
    try {
      const [tenants, registry] = await Promise.all([
        consoleApi<Tenant[]>("/admin/tenants"),
        consoleApi<{ models: Model[] }>("/models"),
      ]);
      setRows(tenants);
      setModels(registry.models ?? []);
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const patch = (next: Partial<Tenant>) =>
    setDraft((current) => (current ? { ...current, ...next } : current));
  const open = (tenant: Tenant, exists: boolean) => {
    setDraft(JSON.parse(JSON.stringify(tenant)) as Tenant);
    setEditing(exists);
    setValidation([]);
    setDomainsText(tenant.domains.join(", "));
  };
  const selectedTenantId = draft?.tenantId ?? "";
  useEffect(() => {
    setResources({ skills: [], mcpServers: [] });
    if (!editing || !selectedTenantId) return;
    let active = true;
    consoleApi<{ skills: ResourceOption[]; mcpServers: ResourceOption[] }>(
      `/admin/tenant-root/${encodeURIComponent(selectedTenantId)}/resources`,
    )
      .then((value) => {
        if (active) setResources(value);
      })
      .catch((error) => {
        if (active) setNotice(errorText(error));
      });
    return () => {
      active = false;
    };
  }, [selectedTenantId, editing]);
  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setNotice("");
    setValidation([]);
    const body = {
      ...(editing ? {} : { tenant_id: draft.tenantId.trim() }),
      display_name: draft.displayName,
      domains: split(domainsText),
      enabled_skills: draft.enabledSkills ?? [],
      enabled_mcp_servers: draft.enabledMcpServers ?? [],
      disabled: draft.disabled,
      ...(scope.isPlatform
        ? { model_policy: draft.modelPolicy, quota: draft.quota }
        : {}),
    };
    try {
      const result = await consoleApi<Tenant | { config: Tenant }>(
        editing
          ? `/admin/tenants/${encodeURIComponent(draft.tenantId)}`
          : "/admin/tenants",
        jsonBody(editing ? "PATCH" : "POST", body),
      );
      const saved = "config" in result ? result.config : result;
      open(saved, true);
      await load();
      setNotice(t("租户配置已保存。", "Tenant saved."));
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const validate = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      const result = await consoleApi<{ checks: typeof validation }>(
        `/admin/tenants/${encodeURIComponent(draft.tenantId)}/validate`,
      );
      setValidation(result.checks);
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="page-container mx-auto max-w-6xl space-y-5 p-5 sm:p-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{t("租户管理", "Tenants")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t(
              "以稳定租户 ID 管理身份域、可用能力、模型和额度。无域名租户同样适用。",
              "Manage stable tenant identities, optional domains, capabilities, models and budgets.",
            )}
          </p>
        </div>
        {scope.isPlatform && (
          <button
            className={action}
            onClick={() => {
              open(blank(), false);
            }}
          >
            {t("新建租户", "New tenant")}
          </button>
        )}
      </header>
      <Notice>{notice}</Notice>
      <section className="overflow-x-auto glass-panel">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              {[
                t("租户", "Tenant"),
                t("身份域", "Identity domains"),
                t("状态", "Status"),
                t("操作", "Actions"),
              ].map((label) => (
                <th className="p-3 font-medium" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((tenant) => (
              <tr className="border-t" key={tenant.tenantId}>
                <td className="p-3">
                  <span className="font-medium">
                    {tenant.displayName || tenant.tenantId}
                  </span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {tenant.tenantId}
                  </span>
                </td>
                <td className="p-3">
                  {tenant.domains.join(", ") ||
                    t("无域名映射", "No domain mapping")}
                </td>
                <td className="p-3">
                  {tenant.disabled
                    ? t("已停用", "Disabled")
                    : t("启用", "Enabled")}
                </td>
                <td className="p-3">
                  <button
                    className={action}
                    onClick={() => {
                      open(tenant, true);
                    }}
                  >
                    {t("编辑", "Edit")}
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
              {t("暂无可管理租户。", "No tenants in your scope.")}
            </p>
          )
        )}
      </section>
      {draft && (
        <>
          <section className="space-y-4 glass-panel p-5">
            <h2 className="font-medium">
              {editing
                ? t("编辑租户", "Edit tenant")
                : t("创建租户", "Create tenant")}
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("稳定租户 ID", "Stable tenant ID")}>
                <input
                  className={control}
                  value={draft.tenantId}
                  disabled={editing}
                  onChange={(e) => patch({ tenantId: e.target.value })}
                />
              </Field>
              <Field label={t("显示名称", "Display name")}>
                <input
                  className={control}
                  value={draft.displayName}
                  onChange={(e) => patch({ displayName: e.target.value })}
                />
              </Field>
              <Field
                label={t(
                  "身份域（逗号分隔，可留空）",
                  "Identity domains (comma separated, optional)",
                )}
              >
                <input
                  className={control}
                  value={domainsText}
                  onChange={(e) => setDomainsText(e.target.value)}
                />
              </Field>
              {editing ? (
                <>
                  <ResourceChecklist
                    label="租户允许的 Skills"
                    options={resources.skills}
                    selected={draft.enabledSkills ?? []}
                    onChange={(enabledSkills) => patch({ enabledSkills })}
                  />
                  <ResourceChecklist
                    label="租户允许的 MCP 服务器"
                    options={resources.mcpServers}
                    selected={draft.enabledMcpServers ?? []}
                    onChange={(enabledMcpServers) =>
                      patch({ enabledMcpServers })
                    }
                  />
                  <p className="text-xs text-muted-foreground sm:col-span-2">
                    空列表表示不允许。还需在 Root
                    绑定资源，并通过权限组分配给用户。
                  </p>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  先保存租户，再选择允许的 Skills 和 MCP。
                </p>
              )}
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.disabled}
                  onChange={(e) => patch({ disabled: e.target.checked })}
                />
                {t("停用租户", "Disable tenant")}
              </label>
            </div>
            {scope.isPlatform && (
              <>
                <h3 className="border-t pt-4 text-sm font-medium">
                  {t("模型与额度", "Models and budgets")}
                </h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label={t("限制可用模型", "Restrict allowed models")}>
                    <span className="flex gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.modelPolicy.allowedModels != null}
                        onChange={(e) =>
                          patch({
                            modelPolicy: {
                              ...draft.modelPolicy,
                              allowedModels: e.target.checked ? [] : null,
                            },
                          })
                        }
                      />
                      {t("启用模型白名单", "Enable model allow-list")}
                    </span>
                    {draft.modelPolicy.allowedModels != null && (
                      <div className="max-h-48 space-y-2 overflow-auto rounded-md border p-3">
                        {models.map((model) => (
                          <label className="flex gap-2 text-sm" key={model.id}>
                            <input
                              type="checkbox"
                              checked={
                                draft.modelPolicy.allowedModels?.includes(
                                  model.id,
                                ) ?? false
                              }
                              onChange={(e) =>
                                patch({
                                  modelPolicy: {
                                    ...draft.modelPolicy,
                                    allowedModels: e.target.checked
                                      ? [
                                          ...(draft.modelPolicy.allowedModels ??
                                            []),
                                          model.id,
                                        ]
                                      : (
                                          draft.modelPolicy.allowedModels ?? []
                                        ).filter((id) => id !== model.id),
                                  },
                                })
                              }
                            />
                            {model.label || model.name || model.id}
                          </label>
                        ))}
                      </div>
                    )}
                  </Field>
                  <Field label={t("默认模型", "Default model")}>
                    <select
                      className={control}
                      value={draft.modelPolicy.defaultModel ?? ""}
                      onChange={(e) =>
                        patch({
                          modelPolicy: {
                            ...draft.modelPolicy,
                            defaultModel: e.target.value || null,
                          },
                        })
                      }
                    >
                      <option value="">
                        {t("继承平台路由", "Inherit platform routing")}
                      </option>
                      {models
                        .filter(
                          (model) =>
                            draft.modelPolicy.allowedModels == null ||
                            draft.modelPolicy.allowedModels.includes(model.id),
                        )
                        .map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.label || model.name || model.id}
                          </option>
                        ))}
                    </select>
                  </Field>
                  <Field
                    label={t(
                      "LLM 额度（美元，0 表示不限额）",
                      "LLM cap (USD, 0 means unlimited)",
                    )}
                  >
                    <input
                      className={control}
                      type="number"
                      min="0"
                      step="0.01"
                      value={draft.quota.llmBudgetUsd ?? 0}
                      onChange={(e) =>
                        patch({
                          quota: {
                            ...draft.quota,
                            llmBudgetUsd: Number(e.target.value),
                          },
                        })
                      }
                    />
                  </Field>
                  <Field label={t("额度周期", "Budget period")}>
                    <select
                      className={control}
                      value={draft.quota.llmBudgetPeriod ?? "monthly"}
                      onChange={(e) =>
                        patch({
                          quota: {
                            ...draft.quota,
                            llmBudgetPeriod: e.target.value,
                          },
                        })
                      }
                    >
                      {[
                        ["daily", t("每日", "Daily")],
                        ["weekly", t("每周", "Weekly")],
                        ["monthly", t("每月", "Monthly")],
                      ].map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    label={t("提醒阈值（0–1）", "Warning threshold (0–1)")}
                  >
                    <input
                      className={control}
                      type="number"
                      min="0"
                      max="1"
                      step="0.05"
                      value={draft.quota.llmBudgetSoftThreshold ?? 0.8}
                      onChange={(e) =>
                        patch({
                          quota: {
                            ...draft.quota,
                            llmBudgetSoftThreshold: Number(e.target.value),
                          },
                        })
                      }
                    />
                  </Field>
                </div>
                <p className="text-xs text-muted-foreground">
                  {t(
                    "额度控制需在下方租户 Agent 策略或 Root Agent 设置中启用。费用依据模型定价估算。",
                    "Enable enforcement below or in Root Agent settings. Costs use estimated model pricing.",
                  )}
                </p>
              </>
            )}
            <div className="flex gap-3">
              <button
                className={action}
                disabled={busy || !draft.tenantId.trim()}
                onClick={() => void save()}
              >
                {busy ? t("保存中…", "Saving…") : t("保存租户", "Save tenant")}
              </button>
              {editing && (
                <button
                  className={action}
                  disabled={busy}
                  onClick={() => void validate()}
                >
                  {t("检查配置", "Validate")}
                </button>
              )}
              <button
                className={action}
                disabled={busy}
                onClick={() => setDraft(null)}
              >
                {t("关闭", "Close")}
              </button>
            </div>
            {validation.length > 0 && (
              <ul className="space-y-2 text-sm">
                {validation.map((check, index) => (
                  <li
                    key={index}
                    className={
                      check.level === "error"
                        ? "text-destructive"
                        : "text-muted-foreground"
                    }
                  >
                    {check.field}: {check.message}
                  </li>
                ))}
              </ul>
            )}
          </section>
          {editing && scope.isPlatform && (
            <TenantRootEditor
              key={draft.tenantId}
              tenantId={draft.tenantId}
              models={models.map((model) => ({
                id: model.id,
                label: model.label || model.name || model.id,
              }))}
            />
          )}
        </>
      )}
    </main>
  );
}
