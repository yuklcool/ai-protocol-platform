"use client";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { PersonalProfileEditor } from "@/components/agent/PersonalProfileEditor";
import { action, consoleApi, control, errorText, Field, jsonBody, Notice } from "@/components/admin/ConsolePrimitives";
type Account = { uid: string; email: string; disabled: boolean; platformAdmin: boolean };
export default function UsersPage() {
  const { user, loading } = useAuth();
  if (loading) return <main className="page-container p-8">加载中…</main>;
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
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { const [accounts, identity] = await Promise.all([consoleApi<Account[]>("/admin/accounts"), consoleApi<{backend: string}>("/auth/provider")]); setRows(accounts); setProvider(identity.backend); }
    catch (error) { setNotice(errorText(error)); }
  }, []);
  useEffect(() => { if (scope.isAdmin) void load(); }, [scope.isAdmin, load]);
  async function mutate(path: string, method: string, body: object) {
    setBusy(true); setNotice("");
    try { await consoleApi(path, jsonBody(method, body)); await load(); setPassword(""); setResetPassword(""); setNotice("账号已更新。"); }
    catch (error) { setNotice(errorText(error)); }
    finally { setBusy(false); }
  }
  if (scope.state === "loading") return <main className="page-container p-8">正在检查管理权限…</main>;
  if (!scope.isAdmin) return <main className="page-container p-8">仅管理员可管理账号。</main>;
  return <main className="page-container mx-auto max-w-5xl space-y-6 p-8">
    <h1 className="text-2xl font-semibold">用户与个人配置</h1><Notice>{notice}</Notice>
    {provider === "local-jwt" && <form className="glass-panel grid gap-4 p-4 sm:grid-cols-3" onSubmit={event => { event.preventDefault(); void mutate("/admin/accounts", "POST", {email, password}); }}>
      <Field label="新账号邮箱"><input className={control} type="email" required value={email} onChange={event => setEmail(event.target.value)} /></Field>
      <Field label="初始密码（至少 12 位）"><input className={control} type="password" required minLength={12} value={password} onChange={event => setPassword(event.target.value)} /></Field>
      <button className={action} disabled={busy}>创建用户</button>
    </form>}
    <div className="glass-panel overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-3">邮箱</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody>
      {rows.map(row => <tr key={row.uid} className="border-t"><td className="p-3">{row.email}</td><td>{row.platformAdmin ? "管理员" : "用户"}</td><td>{row.disabled ? "已停用" : "正常"}</td><td className="space-x-2 p-2"><button className={action} onClick={() => { setSelected(row); setResetPassword(""); }}>编辑个人配置</button>{!row.platformAdmin && <button className={action} disabled={busy} onClick={() => void mutate(`/admin/accounts/${encodeURIComponent(row.email)}`, "PATCH", {disabled: !row.disabled})}>{row.disabled ? "启用" : "停用"}</button>}</td></tr>)}
    </tbody></table></div>
    {selected && <section className="glass-panel space-y-4 p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">{selected.email}</h2><button className={action} onClick={() => setSelected(null)}>关闭</button></div><PersonalProfileEditor key={selected.uid} uid={selected.uid} email={selected.email} />
      {provider === "local-jwt" && <form className="space-y-3 border-t pt-4" onSubmit={event => { event.preventDefault(); void mutate(`/admin/accounts/${encodeURIComponent(selected.email)}/password`, "POST", {password: resetPassword}); }}>
        <Field label="重置密码（至少 12 位）"><input className={control} type="password" minLength={12} required value={resetPassword} onChange={event => setResetPassword(event.target.value)} /></Field>
        <button className={action} disabled={busy}>重置密码</button>
      </form>}
    </section>}
  </main>;
}
