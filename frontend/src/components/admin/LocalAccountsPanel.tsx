"use client";

import { useCallback, useEffect, useState } from "react";
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

type Account = {
  uid: string;
  email: string;
  tenantId: string;
  disabled: boolean;
  groupTags: string[];
};
type Tenant = { tenantId: string; displayName: string; disabled: boolean };
export function LocalAccountsPanel({
  onSelect,
}: {
  onSelect: (email: string) => void;
}) {
  const t = useConsoleCopy();
  const [rows, setRows] = useState<Account[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [q, setQ] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const load = useCallback(async () => {
    try {
      const [accounts, directory] = await Promise.all([
        consoleApi<Account[]>("/admin/accounts"),
        consoleApi<Tenant[]>("/admin/tenants"),
      ]);
      setRows(accounts);
      setTenants(directory);
    } catch (error) {
      setNotice(errorText(error));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const create = async () => {
    setBusy(true);
    setNotice("");
    try {
      await consoleApi(
        "/admin/accounts",
        jsonBody("POST", { email, password, tenant_id: tenantId }),
      );
      setPassword("");
      setEmail("");
      await load();
      setNotice(t("账号已创建。", "Account created."));
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!editing) return;
    setBusy(true);
    setNotice("");
    try {
      await consoleApi(
        `/admin/accounts/${encodeURIComponent(editing.email)}`,
        jsonBody("PATCH", {
          tenant_id: editing.tenantId,
          disabled: editing.disabled,
        }),
      );
      await load();
      setEditing(null);
      setNotice(
        t(
          "账号已更新，原有登录会话已撤销。",
          "Account updated. Existing sessions were revoked.",
        ),
      );
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="space-y-4 rounded-lg border p-5">
      <h2 className="font-medium">{t("本地账号", "Local accounts")}</h2>
      <Notice>{notice}</Notice>
      <Field label={t("筛选邮箱", "Filter email")}>
        <input
          className={control}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </Field>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              {[
                t("账号", "Account"),
                t("租户", "Tenant"),
                t("状态", "Status"),
                t("操作", "Actions"),
              ].map((label) => (
                <th className="p-2" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows
              .filter((row) =>
                row.email.toLowerCase().includes(q.toLowerCase()),
              )
              .map((row) => (
                <tr key={row.email} className="border-t">
                  <td className="p-2">{row.email}</td>
                  <td className="p-2">
                    {tenants.find((tenant) => tenant.tenantId === row.tenantId)
                      ?.displayName || row.tenantId}
                  </td>
                  <td className="p-2">
                    {row.disabled
                      ? t("已停用", "Disabled")
                      : t("启用", "Enabled")}
                  </td>
                  <td className="space-x-3 whitespace-nowrap p-2">
                    <button
                      className="text-primary"
                      onClick={() => {
                        setEditing({ ...row });
                        setResetPassword("");
                      }}
                    >
                      {t("编辑账号", "Edit account")}
                    </button>
                    <button
                      className="text-primary"
                      onClick={() => onSelect(row.email)}
                    >
                      {t("管理分组", "Manage groups")}
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="p-3 text-sm text-muted-foreground">
            {t("暂无账号。", "No accounts.")}
          </p>
        )}
      </div>
      <form
        className="grid gap-3 rounded-md border p-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
      >
        <h3 className="text-sm font-medium sm:col-span-2">
          {t("创建账号", "Create account")}
        </h3>
        <Field label={t("邮箱", "Email")}>
          <input
            className={control}
            type="email"
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field
          label={t(
            "初始密码（至少 12 位）",
            "Initial password (at least 12 characters)",
          )}
        >
          <input
            className={control}
            type="password"
            autoComplete="new-password"
            minLength={12}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <Field label={t("所属租户", "Tenant")}>
          <select
            className={control}
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            required
          >
            <option value="">{t("选择租户", "Select tenant")}</option>
            {tenants
              .filter((tenant) => !tenant.disabled)
              .map((tenant) => (
                <option key={tenant.tenantId} value={tenant.tenantId}>
                  {tenant.displayName || tenant.tenantId}
                </option>
              ))}
          </select>
        </Field>
        <div className="flex items-end">
          <button className={action} disabled={busy}>
            {busy ? t("处理中…", "Working…") : t("创建账号", "Create account")}
          </button>
        </div>
      </form>
      {editing && (
        <section className="space-y-3 rounded-md border p-4">
          <h3 className="break-all text-sm font-medium">{editing.email}</h3>
          <Field label={t("所属租户", "Tenant")}>
            <select
              className={control}
              value={editing.tenantId}
              onChange={(e) =>
                setEditing((current) =>
                  current ? { ...current, tenantId: e.target.value } : current,
                )
              }
            >
              {tenants.map((tenant) => (
                <option
                  key={tenant.tenantId}
                  value={tenant.tenantId}
                  disabled={tenant.disabled}
                >
                  {tenant.displayName || tenant.tenantId}
                </option>
              ))}
            </select>
          </Field>
          <label className="flex gap-2 text-sm">
            <input
              type="checkbox"
              checked={editing.disabled}
              onChange={(e) =>
                setEditing((current) =>
                  current
                    ? { ...current, disabled: e.target.checked }
                    : current,
                )
              }
            />
            {t("停用账号", "Disable account")}
          </label>
          <div className="flex gap-3">
            <button
              className={action}
              disabled={busy}
              onClick={() => void save()}
            >
              {t("保存账号", "Save account")}
            </button>
            <button
              className={action}
              onClick={() => {
                setEditing(null);
                setResetPassword("");
              }}
            >
              {t("关闭", "Close")}
            </button>
          </div>
          <Field
            label={t(
              "新密码（至少 12 位）",
              "New password (at least 12 characters)",
            )}
          >
            <input
              className={control}
              type="password"
              autoComplete="new-password"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
            />
          </Field>
          <button
            className={action}
            disabled={busy || resetPassword.length < 12}
            onClick={async () => {
              if (
                !window.confirm(
                  t(
                    "重置密码并撤销该账号的所有登录会话？",
                    "Reset password and revoke this account's existing sessions?",
                  ),
                )
              )
                return;
              setBusy(true);
              try {
                await consoleApi(
                  `/admin/accounts/${encodeURIComponent(editing.email)}/password`,
                  jsonBody("POST", { password: resetPassword }),
                );
                setResetPassword("");
                setNotice(
                  t(
                    "密码已重置，原有登录会话已撤销。",
                    "Password reset. Existing sessions were revoked.",
                  ),
                );
              } catch (error) {
                setNotice(errorText(error));
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("重置密码", "Reset password")}
          </button>
        </section>
      )}
    </section>
  );
}
