"use client";

import { useEffect, useState } from "react";
import {
  action,
  consoleApi,
  control,
  errorText,
  Field,
  jsonBody,
  Notice,
  useConsoleCopy,
} from "./ConsolePrimitives";

type Binding = "skills" | "tools" | "mcpServers" | "knowledge";
type Option = { id: string; label: string };
type Override = {
  model?: string;
  instructions?: string;
  budgetEnabled?: boolean;
} & Partial<Record<Binding, string[]>>;
type Catalog = Record<Binding, Option[]>;

export function TenantRootEditor({
  tenantId,
  models,
}: {
  tenantId: string;
  models: Option[];
}) {
  const t = useConsoleCopy();
  const [override, setOverride] = useState<Override>({});
  const [catalog, setCatalog] = useState<Catalog>({
    skills: [],
    tools: [],
    mcpServers: [],
    knowledge: [],
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const path = `/admin/tenant-root/${encodeURIComponent(tenantId)}`;
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      consoleApi<{ override: Override }>(path),
      consoleApi<Catalog>(`${path}/resources`),
    ])
      .then(([policy, resources]) => {
        if (!cancelled) {
          setOverride(policy.override);
          setCatalog(resources);
        }
      })
      .catch((error) => {
        if (!cancelled) setNotice(errorText(error));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);
  const save = async () => {
    setBusy(true);
    setNotice("");
    try {
      const saved = await consoleApi<{ override: Override }>(
        path,
        jsonBody("PUT", { override }),
      );
      setOverride(saved.override);
      setNotice(t("租户 Agent 策略已保存。", "Tenant Agent policy saved."));
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const labels: Record<Binding, string> = {
    skills: "Skills",
    tools: "Tools",
    mcpServers: "MCP Servers",
    knowledge: t("知识来源", "Knowledge sources"),
  };
  if (loading)
    return (
      <p className="p-4 text-sm">
        {t("加载租户 Agent 策略…", "Loading tenant Agent policy…")}
      </p>
    );
  return (
    <section className="space-y-4 glass-panel p-5">
      <h2 className="font-medium">
        {t("租户 Agent 策略", "Tenant Agent policy")}
      </h2>
      <p className="text-sm text-muted-foreground">
        {t(
          "未覆盖的配置继承平台 Root Agent。自定义空列表表示不绑定任何资源；资源仍受租户及用户权限限制。",
          "Unset fields inherit Root defaults. An empty custom list binds no resources. Tenant and user permissions still apply.",
        )}
      </p>
      <Notice>{notice}</Notice>
      <Field label={t("模型", "Model")}>
        <select
          className={control}
          value={override.model ?? ""}
          onChange={(e) =>
            setOverride((current) => ({
              ...current,
              model: e.target.value || undefined,
            }))
          }
        >
          <option value="">
            {t("继承平台配置", "Inherit platform setting")}
          </option>
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("额度控制", "Budget enforcement")}>
        <select
          className={control}
          value={
            override.budgetEnabled === undefined
              ? "inherit"
              : String(override.budgetEnabled)
          }
          onChange={(e) =>
            setOverride((current) => ({
              ...current,
              budgetEnabled:
                e.target.value === "inherit"
                  ? undefined
                  : e.target.value === "true",
            }))
          }
        >
          <option value="inherit">
            {t("继承平台配置", "Inherit platform setting")}
          </option>
          <option value="true">{t("启用", "Enabled")}</option>
          <option value="false">{t("关闭", "Disabled")}</option>
        </select>
      </Field>
      <Field
        label={t("系统指令覆盖", "System instructions override")}
        hint={t(
          "取消自定义后继承平台指令。",
          "Disable customization to inherit platform instructions.",
        )}
      >
        <span className="flex gap-2 text-sm">
          <input
            type="checkbox"
            checked={override.instructions !== undefined}
            onChange={(e) =>
              setOverride((current) => ({
                ...current,
                instructions: e.target.checked ? "" : undefined,
              }))
            }
          />
          {t("自定义指令", "Customize instructions")}
        </span>
        {override.instructions !== undefined && (
          <textarea
            className={control}
            rows={5}
            value={override.instructions}
            onChange={(e) =>
              setOverride((current) => ({
                ...current,
                instructions: e.target.value,
              }))
            }
          />
        )}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        {(Object.keys(labels) as Binding[]).map((key) => (
          <section key={key} className="space-y-2 rounded-md border p-3">
            <label className="flex gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={override[key] !== undefined}
                onChange={(e) =>
                  setOverride((current) => ({
                    ...current,
                    [key]: e.target.checked ? [] : undefined,
                  }))
                }
              />
              {labels[key]} · {t("自定义", "Customize")}
            </label>
            {override[key] !== undefined && (
              <div className="max-h-48 space-y-2 overflow-auto">
                {catalog[key].length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    {t(
                      "该租户暂无可绑定资源。",
                      "No resources available for this tenant.",
                    )}
                  </p>
                )}
                {catalog[key].map((option) => (
                  <label key={option.id} className="flex gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={override[key]?.includes(option.id) ?? false}
                      onChange={(e) =>
                        setOverride((current) => ({
                          ...current,
                          [key]: e.target.checked
                            ? [...(current[key] ?? []), option.id]
                            : (current[key] ?? []).filter(
                                (id) => id !== option.id,
                              ),
                        }))
                      }
                    />
                    <span className="break-words">{option.label}</span>
                  </label>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
      <button className={action} disabled={busy} onClick={() => void save()}>
        {busy
          ? t("保存中…", "Saving…")
          : t("保存 Agent 策略", "Save Agent policy")}
      </button>
    </section>
  );
}
