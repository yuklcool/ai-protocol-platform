"use client";
import { useEffect, useState } from "react";
import { ResourceChecklist, type ResourceOption } from "@/components/admin/ResourceChecklist";
import { consoleApi, errorText, Field, jsonBody } from "@/components/admin/ConsolePrimitives";
type Profile = { skills: string[]; information: string };
export function PersonalProfileEditor({ uid, email }: { uid: string; email?: string }) {
  const [profile, setProfile] = useState<Profile>({ skills: [], information: "" });
  const [options, setOptions] = useState<ResourceOption[]>([]);
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"success" | "danger">("danger");
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const path = email ? `/admin/accounts/${encodeURIComponent(email)}/profile` : "/auth/profile";
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setReady(false); setNotice(""); setNoticeTone("danger");
    const skillPath = email ? `/admin/accounts/${encodeURIComponent(email)}/skills` : `/skills?ownerId=${encodeURIComponent(uid)}&limit=200`;
    Promise.all([consoleApi<Profile>(path), consoleApi<Array<{skillId: string; displayName: string; name: string; ownerId?: string}>>(skillPath)])
      .then(([value, skills]) => { if (!cancelled) { setReady(true); setProfile(value); setOptions(skills.filter(skill => skill.ownerId === undefined || skill.ownerId === uid).map(skill => ({ id: skill.skillId, label: skill.displayName || skill.name }))); } })
      .catch(error => { if (!cancelled) setNotice(errorText(error)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [uid, email, path, revision]);
  async function save() {
    setBusy(true); setNotice(""); setNoticeTone("danger");
    try { setProfile(await consoleApi<Profile>(path, jsonBody("PUT", profile))); setNoticeTone("success"); setNotice("个人配置已保存，下次调用立即生效。"); }
    catch (error) { setNotice(errorText(error)); }
    finally { setBusy(false); }
  }
  return <section className="glass-panel space-y-4 p-5">
    <p className="notice notice--info">公共 Skill、工具和 MCP 由 Agent 配置。这里补充此用户专有的 Skill 和个人信息。</p>
    {notice && <p className={`notice notice--${noticeTone}`} role={noticeTone === "success" ? "status" : "alert"}>{notice}</p>}
    {loading ? <p className="notice notice--info" role="status">正在加载个人配置…</p> : !ready ? <button type="button" className="button-secondary min-h-11 px-4 py-2 text-sm" onClick={() => setRevision(value => value + 1)}>重试加载</button> : <>
      <ResourceChecklist label="个人专有 Skill" options={options} selected={profile.skills} disabled={busy} onChange={skills => setProfile({...profile, skills})} />
      <Field label="个人信息与偏好" hint="仅用于此用户的对话，请填写希望助手记住的信息。">
        <textarea className="glass-control min-h-40 w-full px-3 py-2 text-sm" maxLength={20000} value={profile.information} disabled={busy} onChange={event => setProfile({...profile, information: event.target.value})} />
      </Field>
      <button type="button" className="button-primary min-h-11 px-4 py-2 text-sm" disabled={busy} onClick={() => void save()}>{busy ? "正在保存…" : "保存个人配置"}</button>
    </>}
  </section>;
}
