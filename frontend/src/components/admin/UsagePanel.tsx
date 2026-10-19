"use client";

import { useEffect, useState } from "react";
import {
  action,
  consoleApi,
  control,
  errorText,
  Notice,
  useConsoleCopy,
} from "./ConsolePrimitives";

type Stats = {
  calls: number;
  inputTokens: number;
  outputTokens: number;
  estimatedCostUsd: number;
  unpricedCalls: number;
};
type TenantUsage = Stats & {
  tenantId: string;
  label: string;
  quotaUsd: number | null;
  chargedUsd: number;
  heldUsd: number;
  period: string;
};
type Usage = {
  totals: Stats;
  tenants: TenantUsage[];
  models: Array<Omit<Stats, "unpricedCalls"> & { modelId: string }>;
};
export function UsagePanel() {
  const t = useConsoleCopy();
  const [data, setData] = useState<Usage | null>(null);
  const [options, setOptions] = useState<Array<{ id: string; label: string }>>(
    [],
  );
  const [days, setDays] = useState("30");
  const [tenant, setTenant] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice("");
    const params = new URLSearchParams({
      days,
      ...(tenant ? { tenant_id: tenant } : {}),
    });
    consoleApi<Usage>(`/admin/usage?${params}`)
      .then((result) => {
        if (cancelled) return;
        if (!result.totals || !Array.isArray(result.tenants))
          throw new Error("Invalid usage response");
        setData(result);
        if (!tenant)
          setOptions(
            result.tenants.map((row) => ({
              id: row.tenantId,
              label: row.label,
            })),
          );
      })
      .catch((error) => {
        if (!cancelled) {
          setData(null);
          setNotice(errorText(error));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [days, tenant, nonce]);
  const cost = (value: number) => `$${value.toFixed(6)}`;
  const totals = data?.totals;
  return (
    <section className="mb-6 space-y-4 glass-panel p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="mr-auto text-base font-semibold">
          {t("用量与额度", "Usage and budgets")}
        </h2>
        <select
          aria-label={t("用量时间范围", "Usage time range")}
          className={`${control} w-auto`}
          value={days}
          onChange={(e) => setDays(e.target.value)}
        >
          {[7, 30, 90].map((value) => (
            <option key={value} value={value}>
              {t(`最近 ${value} 天`, `Last ${value} days`)}
            </option>
          ))}
        </select>
        <select
          aria-label={t("用量租户", "Usage tenant")}
          className={`${control} w-auto`}
          value={tenant}
          onChange={(e) => setTenant(e.target.value)}
        >
          <option value="">
            {t("全部授权租户", "All authorized tenants")}
          </option>
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          className={action}
          disabled={loading}
          onClick={() => setNonce((value) => value + 1)}
        >
          {t("刷新用量", "Refresh usage")}
        </button>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        {t(
          "Token 按模型返回的用量持久化记录；费用为估算值。历史记录从启用此版本后开始累计，未返回用量的调用不计入统计。额度占用包含尚未结算的预留金额。",
          "Tokens use persisted provider-reported usage; costs are estimates. Accounting starts with this version. Calls without reported usage are excluded. Budget charges include unsettled holds.",
        )}
      </p>
      <Notice>{notice}</Notice>
      {loading && (
        <p role="status" className="text-sm">
          {t("正在加载用量…", "Loading usage…")}
        </p>
      )}
      {totals && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              [t("模型调用", "Model calls"), totals.calls.toLocaleString()],
              [
                t("输入 Token", "Input tokens"),
                totals.inputTokens.toLocaleString(),
              ],
              [
                t("输出 Token", "Output tokens"),
                totals.outputTokens.toLocaleString(),
              ],
              [t("估算费用", "Estimated cost"), cost(totals.estimatedCostUsd)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-2 text-xl font-medium">{value}</p>
              </div>
            ))}
          </div>
          {totals.unpricedCalls > 0 && (
            <Notice>
              {t(
                `${totals.unpricedCalls} 次调用缺少模型定价，费用统计不含这些调用的成本。`,
                `${totals.unpricedCalls} calls have no known pricing; their cost is excluded.`,
              )}
            </Notice>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  {[
                    t("租户", "Tenant"),
                    t("估算费用", "Estimated cost"),
                    t("周期额度", "Period cap"),
                    t("已占用 / 其中预留", "Charged / held"),
                    t("周期", "Period"),
                  ].map((label) => (
                    <th className="p-2 font-medium" key={label}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.tenants.map((row) => (
                  <tr key={row.tenantId} className="border-t">
                    <td className="p-2">{row.label}</td>
                    <td className="p-2">{cost(row.estimatedCostUsd)}</td>
                    <td className="p-2">
                      {row.quotaUsd
                        ? cost(row.quotaUsd)
                        : t("不限额", "Unlimited")}
                    </td>
                    <td className="p-2">
                      {cost(row.chargedUsd)} / {cost(row.heldUsd)}
                    </td>
                    <td className="p-2">
                      {row.period === "daily"
                        ? t("每日", "Daily")
                        : row.period === "weekly"
                          ? t("每周", "Weekly")
                          : t("每月", "Monthly")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.tenants.length === 0 && (
              <p className="p-3 text-sm text-muted-foreground">
                {t("暂无租户用量。", "No tenant usage.")}
              </p>
            )}
          </div>
          {data.models.length > 0 && (
            <details>
              <summary className="cursor-pointer text-sm">
                {t("按模型查看", "View by model")}
              </summary>
              <div className="mt-3 space-y-2">
                {data.models.map((model) => (
                  <p
                    key={model.modelId}
                    className="break-all text-xs text-muted-foreground"
                  >
                    {model.modelId} · {model.calls} ·{" "}
                    {model.inputTokens + model.outputTokens} Token ·{" "}
                    {cost(model.estimatedCostUsd)}
                  </p>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}
