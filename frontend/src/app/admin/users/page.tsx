"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { ResourceChecklist } from "@/components/admin/ResourceChecklist";
import {
  action,
  consoleApi,
  control,
  errorText,
  Field,
  jsonBody,
  Notice,
} from "@/components/admin/ConsolePrimitives";

type Account = {
  email: string;
  uid: string;
  tenantId: string;
  permissionGroupIds: string[];
  disabled: boolean;
  platformAdmin: boolean;
};
type Tenant = { tenantId: string; displayName: string; disabled: boolean };
type Group = {
  id: string;
  tenantId: string;
  label: string;
  role: "member" | "tenant-admin";
};
type Access = {
  skills: { id: string; label: string }[];
  mcpServers: string[];
  reason: string;
};

export default function UsersPage() {
  const { user, loading } = useAuth();
  if (loading) return <main className="page-container p-8">加载中…</main>;
  if (!user) return <SignInRequired />;
  return <Users />;
}
function Users() {
  const scope = useAdminScope();
  const [rows, setRows] = useState<Account[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [provider, setProvider] = useState("");
  const [draft, setDraft] = useState<Account | null>(null);
  const [creating, setCreating] = useState(false);
  const [password, setPassword] = useState("");
  const [q, setQ] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{
    email: string;
    result: Access;
  } | null>(null);
  const load = useCallback(async () => {
    try {
      const [accounts, directory, permissions, identity] = await Promise.all([
        consoleApi<Account[]>("/admin/accounts"),
        consoleApi<Tenant[]>("/admin/tenants"),
        consoleApi<Group[]>("/admin/groups"),
        consoleApi<{ backend: string }>("/auth/provider"),
      ]);
      setRows(accounts);
      setTenants(directory);
      setGroups(permissions);
      setProvider(identity.backend);
    } catch (error) {
      setNotice(errorText(error));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const patch = (next: Partial<Account>) =>
    setDraft((current) => (current ? { ...current, ...next } : current));
  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setNotice("");
    setPreview(null);
    try {
      const endpoint = `/admin/accounts${creating ? "" : `/${encodeURIComponent(draft.email)}`}`;
      await consoleApi(
        endpoint,
        jsonBody(creating ? "POST" : "PATCH", {
          ...(creating
            ? { email: draft.email, password, tenant_id: draft.tenantId }
            : { disabled: draft.disabled }),
          permission_group_ids: draft.permissionGroupIds,
        }),
      );
      setPassword("");
      setDraft(null);
      await load();
      setNotice("账号与权限组已保存，授权在后续请求生效。");
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const resetPassword = async () => {
    if (!draft || !password) return;
    setBusy(true);
    try {
      await consoleApi(
        `/admin/accounts/${encodeURIComponent(draft.email)}/password`,
        jsonBody("POST", { password }),
      );
      setPassword("");
      setNotice("密码已重置，原有令牌已失效。");
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const inspect = async (email: string) => {
    setBusy(true);
    setPreview(null);
    try {
      setPreview({
        email,
        result: await consoleApi<Access>(
          "/admin/access/check",
          jsonBody("POST", { email }),
        ),
      });
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="page-container mx-auto max-w-6xl space-y-5 p-5 sm:p-8">
      <header className="flex flex-wrap justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">用户管理</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            选择用户所属租户和权限组，即可完成授权。平台超级管理员账号受保护。
          </p>
        </div>
        {provider === "local-jwt" && (
          <button
            className={action}
            disabled={busy || !tenants.some((tenant) => !tenant.disabled)}
            onClick={() => {
              setCreating(true);
              setPassword("");
              setDraft({
                email: "",
                uid: "",
                tenantId:
                  tenants.find((tenant) => !tenant.disabled)?.tenantId ?? "",
                permissionGroupIds: [],
                disabled: false,
                platformAdmin: false,
              });
            }}
          >
            新建用户
          </button>
        )}
      </header>
      <Notice>{notice}</Notice>
      {provider === "oidc" && (
        <p className="text-sm text-muted-foreground">
          登录身份和密码由 OIDC
          身份源管理，此处管理已关联账号的权限组与启用状态。
        </p>
      )}
      {draft && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
          className="space-y-4 glass-panel p-5"
        >
          <h2 className="font-medium">
            {creating ? "新建用户" : `编辑 ${draft.email}`}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="邮箱">
              <input
                className={control}
                type="email"
                value={draft.email}
                disabled={!creating || busy}
                onChange={(event) => patch({ email: event.target.value })}
                required
              />
            </Field>
            <Field label="所属租户">
              <select
                className={control}
                value={draft.tenantId}
                disabled={!creating || busy}
                onChange={(event) =>
                  patch({
                    tenantId: event.target.value,
                    permissionGroupIds: [],
                  })
                }
                required
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
          </div>
          <ResourceChecklist
            label="权限组（可多选）"
            options={groups
              .filter((group) => group.tenantId === draft.tenantId)
              .map((group) => ({ id: group.id, label: group.label }))}
            selected={draft.permissionGroupIds}
            onChange={(permissionGroupIds) => patch({ permissionGroupIds })}
          />
          {provider === "local-jwt" && (
            <div className="flex items-end gap-2">
              <Field
                label={
                  creating ? "初始密码（至少 12 位）" : "重置密码（至少 12 位）"
                }
              >
                <input
                  className={control}
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  required={creating}
                  minLength={12}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </Field>
              {!creating && (
                <button
                  className={action}
                  type="button"
                  disabled={busy || password.length < 12}
                  onClick={() => void resetPassword()}
                >
                  重置密码
                </button>
              )}
            </div>
          )}
          {!creating && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.disabled}
                onChange={(event) => patch({ disabled: event.target.checked })}
              />
              停用账号
            </label>
          )}
          <div className="flex gap-2">
            <button className={action} disabled={busy} type="submit">
              保存
            </button>
            <button
              className={action}
              type="button"
              disabled={busy}
              onClick={() => {
                setDraft(null);
                setPassword("");
              }}
            >
              取消
            </button>
          </div>
        </form>
      )}
      <Field label="搜索用户">
        <input
          className={control}
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="按邮箱搜索"
        />
      </Field>
      <div className="space-y-3">
        {rows
          .filter((row) => row.email.toLowerCase().includes(q.toLowerCase()))
          .map((row) => (
            <article
              className="flex flex-wrap justify-between gap-3 glass-panel p-4"
              key={row.email}
            >
              <div>
                <h2 className="font-medium">{row.email}</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {tenants.find((tenant) => tenant.tenantId === row.tenantId)
                    ?.displayName || row.tenantId}{" "}
                  · {row.disabled ? "已停用" : "已启用"} ·{" "}
                  {row.platformAdmin
                    ? "平台超级管理员"
                    : row.permissionGroupIds
                        .map(
                          (id) =>
                            groups.find((group) => group.id === id)?.label,
                        )
                        .filter(Boolean)
                        .join("、") || "未分配权限组"}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  className={action}
                  disabled={
                    busy ||
                    row.platformAdmin ||
                    (!scope.isPlatform &&
                      row.permissionGroupIds.some(
                        (id) =>
                          groups.find((group) => group.id === id)?.role ===
                          "tenant-admin",
                      ))
                  }
                  onClick={() => {
                    setCreating(false);
                    setDraft({ ...row });
                    setPassword("");
                  }}
                >
                  编辑
                </button>
                <button
                  className={action}
                  disabled={busy}
                  onClick={() => void inspect(row.email)}
                >
                  有效权限
                </button>
              </div>
            </article>
          ))}
      </div>
      {preview && (
        <section className="glass-panel p-5">
          <h2 className="font-medium">{preview.email} 的有效权限</h2>
          <p className="my-2 text-sm text-muted-foreground">
            {preview.result.reason}
          </p>
          <p className="text-sm">
            Skills：
            {preview.result.skills.map((skill) => skill.label).join("、") ||
              "无"}
          </p>
          <p className="mt-2 text-sm">
            MCP：{preview.result.mcpServers.join("、") || "无"}
          </p>
        </section>
      )}
    </main>
  );
}
