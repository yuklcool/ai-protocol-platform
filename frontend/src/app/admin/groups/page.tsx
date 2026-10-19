"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { SignInRequired } from "@/components/chat/SignInRequired";
import {
  ResourceChecklist,
  type ResourceOption,
} from "@/components/admin/ResourceChecklist";
import {
  action,
  consoleApi,
  control,
  errorText,
  Field,
  jsonBody,
  Notice,
} from "@/components/admin/ConsolePrimitives";

type Group = {
  id: string;
  tenantId: string;
  label: string;
  description: string;
  skills: string[];
  mcpServers: string[];
  role: "member" | "tenant-admin";
};
type Tenant = { tenantId: string; displayName: string; disabled: boolean };
type Resources = { skills: ResourceOption[]; mcpServers: ResourceOption[] };
const blank = (tenantId: string): Group => ({
  id: "",
  tenantId,
  label: "",
  description: "",
  skills: [],
  mcpServers: [],
  role: "member",
});

export default function GroupsPage() {
  const { user, loading } = useAuth();
  if (loading) return <main className="page-container p-8">加载中…</main>;
  if (!user) return <SignInRequired />;
  return <Groups />;
}
function Groups() {
  const scope = useAdminScope();
  const [groups, setGroups] = useState<Group[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [draft, setDraft] = useState<Group | null>(null);
  const [resources, setResources] = useState<Resources>({
    skills: [],
    mcpServers: [],
  });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const [rows, directory] = await Promise.all([
        consoleApi<Group[]>("/admin/groups"),
        consoleApi<Tenant[]>("/admin/tenants"),
      ]);
      setGroups(rows);
      setTenants(directory);
    } catch (error) {
      setNotice(errorText(error));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const tenantId = draft?.tenantId ?? "";
  useEffect(() => {
    setResources({ skills: [], mcpServers: [] });
    if (!tenantId) return;
    let active = true;
    consoleApi<Resources>(
      `/admin/groups/resources?tenant_id=${encodeURIComponent(tenantId)}`,
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
  }, [tenantId]);
  const patch = (value: Partial<Group>) =>
    setDraft((current) => (current ? { ...current, ...value } : current));
  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setNotice("");
    try {
      await consoleApi(
        `/admin/groups${draft.id ? `/${encodeURIComponent(draft.id)}` : ""}`,
        jsonBody(draft.id ? "PUT" : "POST", draft),
      );
      setDraft(null);
      await load();
      setNotice("权限组已保存，后续请求立即使用新授权。");
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (group: Group) => {
    if (
      !window.confirm(`删除“${group.label}”？成员将立即失去这个组提供的授权。`)
    )
      return;
    setBusy(true);
    try {
      await consoleApi(`/admin/groups/${encodeURIComponent(group.id)}`, {
        method: "DELETE",
      });
      await load();
      setNotice("权限组已删除。");
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="page-container mx-auto max-w-5xl space-y-5 p-5 sm:p-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">权限组</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            给组选择 Skills 和
            MCP，再在用户页分配组。多个组的授权合并后，仍受租户和当前 Root
            的允许范围约束。
          </p>
        </div>
        <button
          className={action}
          disabled={busy || !tenants.some((tenant) => !tenant.disabled)}
          onClick={() =>
            setDraft(
              blank(tenants.find((tenant) => !tenant.disabled)?.tenantId ?? ""),
            )
          }
        >
          新建权限组
        </button>
      </header>
      <Notice>{notice}</Notice>
      {draft && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
          className="space-y-4 glass-panel p-5"
        >
          <h2 className="font-medium">
            {draft.id ? "编辑权限组" : "新建权限组"}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="所属租户">
              <select
                className={control}
                value={draft.tenantId}
                disabled={!!draft.id || busy}
                onChange={(event) => setDraft(blank(event.target.value))}
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
            <Field label="组名称">
              <input
                className={control}
                value={draft.label}
                onChange={(event) => patch({ label: event.target.value })}
                required
                maxLength={120}
              />
            </Field>
            <Field label="角色">
              <select
                className={control}
                value={draft.role}
                disabled={!scope.isPlatform}
                onChange={(event) =>
                  patch({ role: event.target.value as Group["role"] })
                }
              >
                <option value="member">普通成员</option>
                <option value="tenant-admin">租户管理员</option>
              </select>
            </Field>
            <Field label="说明">
              <input
                className={control}
                value={draft.description}
                onChange={(event) => patch({ description: event.target.value })}
                maxLength={1000}
              />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <ResourceChecklist
              label="允许的 Skills"
              options={resources.skills}
              selected={draft.skills}
              onChange={(skills) => patch({ skills })}
            />
            <ResourceChecklist
              label="允许的 MCP 服务器"
              options={resources.mcpServers}
              selected={draft.mcpServers}
              onChange={(mcpServers) => patch({ mcpServers })}
            />
          </div>
          <div className="flex gap-2">
            <button className={action} disabled={busy} type="submit">
              保存
            </button>
            <button
              className={action}
              disabled={busy}
              type="button"
              onClick={() => setDraft(null)}
            >
              取消
            </button>
          </div>
        </form>
      )}
      <div className="space-y-3">
        {groups.length === 0 && (
          <p className="glass-panel p-5 text-sm text-muted-foreground">
            还没有权限组。普通用户未分配授权时，无法使用额外 Skills 或 MCP。
          </p>
        )}
        {groups.map((group) => (
          <article
            key={group.id}
            className="flex flex-wrap justify-between gap-3 glass-panel p-4"
          >
            <div>
              <h2 className="font-medium">{group.label}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {tenants.find((tenant) => tenant.tenantId === group.tenantId)
                  ?.displayName || group.tenantId}{" "}
                · {group.role === "tenant-admin" ? "租户管理员" : "普通成员"} ·{" "}
                {group.skills.length} 个 Skill · {group.mcpServers.length} 个
                MCP
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className={action}
                disabled={
                  busy || (!scope.isPlatform && group.role === "tenant-admin")
                }
                onClick={() => setDraft({ ...group })}
              >
                编辑
              </button>
              <button
                className={action}
                disabled={
                  busy || (!scope.isPlatform && group.role === "tenant-admin")
                }
                onClick={() => void remove(group)}
              >
                删除
              </button>
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
