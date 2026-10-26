"use client";

import { useCallback, useEffect, useState } from "react";
import { Search, UserPlus, UsersRound } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { PersonalProfileEditor } from "@/components/agent/PersonalProfileEditor";
import { action, consoleApi, control, errorText, Field, jsonBody, Notice } from "@/components/admin/ConsolePrimitives";

type Account = { uid: string; email: string; disabled: boolean; platformAdmin: boolean };

export default function UsersPage() {
  const { user, loading } = useAuth();
  if (loading) return <main className="page-container" role="status">加载中…</main>;
  if (!user) return <SignInRequired />;
  return <Users />;
}

function Users() {
  const scope = useAdminScope();
  const [rows, setRows] = useState<Account[]>([]);
  const [selected, setSelected] = useState<Account | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [notice, setNotice] = useState("");
  const [tone, setTone] = useState<"info" | "success" | "danger">("info");
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [query, setQuery] = useState("");
  const load = useCallback(async () => {
    setListLoading(true);
    setLoadFailed(false);
    try {
      const [accounts, identity] = await Promise.all([
        consoleApi<Account[]>("/admin/accounts"),
        consoleApi<{ backend: string }>("/auth/provider"),
      ]);
      setRows(accounts);
      setProvider(identity.backend);
      return true;
    } catch (error) {
      setTone("danger");
      setNotice(errorText(error));
      setLoadFailed(true);
      return false;
    } finally {
      setListLoading(false);
    }
  }, []);
  useEffect(() => { if (scope.isAdmin) void load(); }, [scope.isAdmin, load]);

  async function mutate(path: string, method: string, body: object) {
    setBusy(true);
    setNotice("");
    try {
      await consoleApi(path, jsonBody(method, body));
      const refreshed = await load();
      setPassword("");
      setResetPassword("");
      if (refreshed) { setTone("success"); setNotice("账号已更新。"); }
    } catch (error) {
      setTone("danger");
      setNotice(errorText(error));
    } finally { setBusy(false); }
  }

  if (scope.state === "loading") return <main className="page-container" role="status">正在检查管理权限…</main>;
  if (scope.state === "error") return <main className="page-container"><div className="notice notice--danger" role="alert">管理权限加载失败。<button type="button" className={action} onClick={() => void scope.recheck()}>重试</button></div></main>;
  if (!scope.isAdmin) return <main className="page-container"><div className="empty-state"><UsersRound aria-hidden="true" /><h1 className="empty-state__title">仅管理员可管理账号</h1><p className="empty-state__desc">如需访问，请联系平台管理员。</p></div></main>;
  const visible = rows.filter((row) => row.email.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return (
    <main className="page-container">
      <div className="page-body space-y-5">
        <header className="page-header">
          <div><h1 className="page-header__title">用户与个人配置</h1><p className="page-header__desc">管理账号、访问状态与个人配置。</p></div>
          {!listLoading && !loadFailed && <span className="badge">{rows.length} 个账号</span>}
        </header>
        <Notice tone={tone}>{notice}</Notice>
        {provider === "local-jwt" && (
          <details className="glass-panel">
            <summary className="min-h-11 cursor-pointer px-4 py-3 text-sm font-medium"><UserPlus className="mr-2 inline h-4 w-4 text-primary" aria-hidden="true" />创建用户</summary>
            <form className="grid items-end gap-4 border-t p-4 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => { event.preventDefault(); void mutate("/admin/accounts", "POST", { email, password }); }}>
              <Field label="新账号邮箱"><input className={control} type="email" autoComplete="off" required value={email} onChange={(event) => setEmail(event.target.value)} /></Field>
              <Field label="初始密码（至少 12 位）"><input className={control} type="password" autoComplete="new-password" required minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} /></Field>
              <button className="button-primary text-sm" disabled={busy}>{busy ? "处理中…" : "创建用户"}</button>
            </form>
          </details>
        )}
        <section className="glass-panel overflow-hidden" aria-label="用户列表">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
            <h2 className="text-sm font-semibold">全部用户</h2>
            <label className="relative w-full sm:w-64"><span className="sr-only">搜索账号邮箱</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><input className="glass-control w-full py-2 pl-9 pr-3 text-sm" type="search" placeholder="搜索账号邮箱…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          </div>
          {listLoading ? <div role="status" className="space-y-3 p-5"><span className="sr-only">正在加载用户…</span>{[1, 2, 3].map((i) => <div key={i} className="skeleton h-10" aria-hidden="true" />)}</div> : loadFailed ?
            <div className="empty-state m-4"><p className="empty-state__title">用户列表加载失败</p><button type="button" className={action} onClick={() => { setNotice(""); void load(); }}>重新加载</button></div> : visible.length === 0 ?
              <div className="empty-state m-4"><p className="empty-state__title">{query ? "没有匹配的账号" : "暂无账号"}</p>{query && <button type="button" className={action} onClick={() => setQuery("")}>清除搜索</button>}</div> :
              <div className="overflow-x-auto"><table className="data-table"><thead><tr><th>邮箱</th><th>角色</th><th>状态</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>
                {visible.map((row) => <tr key={row.uid}><td className="min-w-48 font-medium">{row.email}</td><td><span className={`badge ${row.platformAdmin ? "badge--brand" : ""}`}>{row.platformAdmin ? "管理员" : "用户"}</span></td><td><span className={`badge ${row.disabled ? "badge--warning" : "badge--success"}`}>{row.disabled ? "已停用" : "正常"}</span></td><td><div className="row-actions"><button type="button" className="button-secondary text-xs" onClick={() => { setSelected(row); setResetPassword(""); }}>编辑个人配置</button>{!row.platformAdmin && <button type="button" className={`${row.disabled ? "button-secondary" : "button-danger"} text-xs`} disabled={busy} onClick={() => void mutate(`/admin/accounts/${encodeURIComponent(row.email)}`, "PATCH", { disabled: !row.disabled })}>{row.disabled ? "启用" : "停用"}</button>}</div></td></tr>)}
              </tbody></table></div>}
        </section>
        {selected && <section className="glass-panel space-y-4 p-5" aria-label="编辑用户配置"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="meta-label">正在编辑</p><h2 className="break-all font-semibold">{selected.email}</h2></div><button type="button" className={action} onClick={() => setSelected(null)}>关闭</button></div><PersonalProfileEditor key={selected.uid} uid={selected.uid} email={selected.email} />
          {provider === "local-jwt" && <form className="surface-sunken space-y-3 p-4" onSubmit={(event) => { event.preventDefault(); void mutate(`/admin/accounts/${encodeURIComponent(selected.email)}/password`, "POST", { password: resetPassword }); }}><Field label="重置密码（至少 12 位）"><input className={control} type="password" autoComplete="new-password" minLength={12} required value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} /></Field><button className="button-secondary text-sm" disabled={busy}>重置密码</button></form>}
        </section>}
      </div>
    </main>
  );
}
