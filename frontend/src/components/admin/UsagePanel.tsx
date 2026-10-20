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
type UserUsage = Stats & { userId: string };
type Usage = {
  totals: Stats;
  users: UserUsage[];
  models: Array<Omit<Stats, "unpricedCalls"> & { modelId: string }>;
};
export function UsagePanel() {
  const t = useConsoleCopy();
  const [data, setData] = useState<Usage | null>(null);
  const [options, setOptions] = useState<Array<{ id: string; label: string }>>(
    [],
  );
  const [days, setDays] = useState("30");
  const [userId, setUserId] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice("");
    const params = new URLSearchParams({
      days,
      ...(userId ? { user_id: userId } : {}),
    });
    consoleApi<Usage>(`/admin/usage?${params}`)
      .then((result) => {
        if (cancelled) return;
        if (!result.totals || !Array.isArray(result.users))
          throw new Error("Invalid usage response");
        setData(result);
        if (!userId)
          setOptions(
            result.users.map((row) => ({
              id: row.userId,
              label: row.userId,
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
  }, [days, userId, nonce]);
  const cost = (value: number) => `$${value.toFixed(6)}`;
  const totals = data?.totals;
  return (
    <section className="glass-panel min-w-0 space-y-4 p-4 sm:p-5" aria-busy={loading}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <h2 className="text-base font-semibold">
          {t("用量统计", "Usage")}
        </h2>
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
        <select
          aria-label={t("用量时间范围", "Usage time range")}
          className={`${control} w-auto min-w-0 max-w-full`}
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
          aria-label={t("用户用量", "Usage user")}
          className={`${control} w-auto min-w-0 max-w-full`}
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
        >
          <option value="">
            {t("全部用户", "All users")}
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
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        {t(
          "Token 按模型返回的用量持久化记录；费用为估算值。历史记录从启用此版本后开始累计，未返回用量的调用不计入统计。",
          "Tokens use persisted provider-reported usage; costs are estimates. Accounting starts with this version. Calls without reported usage are excluded.",
        )}
      </p>
      <Notice tone="danger">{notice}</Notice>
      {loading && (
        <p role="status" className="skeleton p-6 text-sm text-muted-foreground">
          {t("正在加载用量…", "Loading usage…")}
        </p>
      )}
      {!loading && totals && (
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
              <div key={label} className="min-w-0 rounded-xl border bg-background/60 p-4">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-2 break-words text-xl font-semibold tabular-nums">{value}</p>
              </div>
            ))}
          </div>
          {totals.unpricedCalls > 0 && (
            <Notice tone="warning">
              {t(
                `${totals.unpricedCalls} 次调用缺少模型定价，费用统计不含这些调用的成本。`,
                `${totals.unpricedCalls} calls have no known pricing; their cost is excluded.`,
              )}
            </Notice>
          )}
          <div className="min-w-0 overflow-x-auto rounded-xl border bg-background/40">
            <table className="data-table min-w-[640px]" aria-label={t("用户用量明细", "Usage by user")}>
              <thead>
                <tr>
                  {[
                    t("用户", "User"), t("模型调用", "Model calls"), t("输入 / 输出 Token", "Input / output tokens"), t("估算费用", "Estimated cost"),
                  ].map((label, index) => (
                    <th className={index > 0 ? "num" : undefined} key={label}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.users.map((row) => (
                  <tr key={row.userId}>
                    <td className="max-w-64 break-words">{row.userId}</td>
                    <td className="num">{row.calls}</td>
                    <td className="num whitespace-nowrap">{row.inputTokens} / {row.outputTokens}</td>
                    <td className="num">{cost(row.estimatedCostUsd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.users.length === 0 && (
              <p className="empty-state text-sm text-muted-foreground">
                {t("暂无用户用量。", "No user usage.")}
              </p>
            )}
          </div>
          {data.models.length > 0 && (
            <details className="rounded-xl border bg-background/40 p-4">
              <summary className="cursor-pointer text-sm">
                {t("按模型查看", "View by model")}
              </summary>
              <div className="mt-3 min-w-0 overflow-x-auto">
                <table className="data-table min-w-[560px]" aria-label={t("模型用量明细", "Usage by model")}>
                  <thead>
                    <tr>
                      <th>{t("模型", "Model")}</th>
                      <th className="num">{t("模型调用", "Model calls")}</th>
                      <th className="num">{t("总 Token", "Total tokens")}</th>
                      <th className="num">{t("估算费用", "Estimated cost")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.models.map((model) => (
                      <tr key={model.modelId}>
                        <td className="max-w-64 break-all">{model.modelId}</td>
                        <td className="num">{model.calls}</td>
                        <td className="num">{model.inputTokens + model.outputTokens}</td>
                        <td className="num">{cost(model.estimatedCostUsd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}
