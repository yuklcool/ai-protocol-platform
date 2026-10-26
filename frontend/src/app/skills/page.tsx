"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Plus, Search, Sparkles } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { useUserSkills } from "@/hooks/useUserSkills";
import { fetchWithAuth } from "@/lib/apiClient";
import { translate } from "@/lib/i18n";

type Profile = { skills: string[]; information: string };
type Availability = "available" | "unbound" | "unknown";
const PROFILE_PATH = "/api/proxy/api/auth/profile";
const AGENT_PATH = "/api/proxy/api/agent";

function readProfile(value: unknown): Profile {
  const profile = value as Partial<Profile> | null;
  if (!profile || !Array.isArray(profile.skills) ||
      !profile.skills.every((id) => typeof id === "string") ||
      typeof profile.information !== "string") {
    throw new Error("Invalid profile response");
  }
  return { skills: profile.skills, information: profile.information };
}

async function getProfile(signal: AbortSignal): Promise<Profile> {
  const response = await fetchWithAuth(PROFILE_PATH, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return readProfile(await response.json());
}

async function checkCapability(skillId: string, signal: AbortSignal): Promise<Availability> {
  if (signal.aborted) return "unknown";
  try {
    const response = await fetchWithAuth(`${AGENT_PATH}/capabilities/${encodeURIComponent(skillId)}`, { signal });
    if (response.status === 404) return "unbound";
    if (!response.ok) return "unknown";
    const value = await response.json();
    return value?.skillId === skillId && value?.skillMetadata && typeof value.skillMetadata === "object"
      ? "available" : "unknown";
  } catch {
    return "unknown";
  }
}

export default function SkillsResourcePage() {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  if (loading) {
    return <main className="page-container text-sm text-muted-foreground" role="status">{translate(locale, "common.loading")}</main>;
  }
  if (!user) return <SignInRequired />;
  return <SkillsResourceInner key={user.uid} userId={user.uid} />;
}

function SkillsResourceInner({ userId }: { userId: string }) {
  const { skills, isLoading, error, retry } = useUserSkills(userId);
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const studioEnabled = process.env.NEXT_PUBLIC_ENABLE_SKILL_STUDIO === "true";
  const [query, setQuery] = useState("");
  const [section, setSection] = useState<"all" | "mine">("all");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileFailed, setProfileFailed] = useState(false);
  const [availability, setAvailability] = useState<Record<string, Availability>>({});
  const [checking, setChecking] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [enableError, setEnableError] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const bindingChanges = useRef(new Set<string>());

  useEffect(() => {
    const controller = new AbortController();
    requestRef.current = controller;
    const { signal } = controller;
    bindingChanges.current.clear();
    setProfile(null);
    setProfileFailed(false);
    setAvailability({});
    setChecking(true);
    setSaving(null);
    setEnableError(false);
    if (isLoading || error) return () => controller.abort();

    void getProfile(signal).then((value) => {
      if (!signal.aborted) setProfile(value);
    }).catch(() => {
      if (!signal.aborted) setProfileFailed(true);
    });

    // /agent 返回 SkillResponse，而非包含 skills 绑定列表的配置对象。
    void (async () => {
      try {
        const response = await fetchWithAuth(AGENT_PATH, { signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const agent = await response.json();
        if (agent?.skillId !== "root-agent" || !agent?.skillMetadata || typeof agent.skillMetadata !== "object") {
          throw new Error("Invalid agent metadata");
        }
        await Promise.all(skills.map(async (skill) => {
          const value = await checkCapability(skill.skillId, signal);
          if (!signal.aborted && !bindingChanges.current.has(skill.skillId)) {
            setAvailability((current) => ({ ...current, [skill.skillId]: value }));
          }
        }));
      } catch {
        // 元数据或授权不可确认时保持 unknown，绝不从 ACL 可见性推断可调用。
      } finally {
        if (!signal.aborted) setChecking(false);
      }
    })();
    return () => controller.abort();
  }, [userId, skills, isLoading, error]);

  async function enableForMe(skillId: string) {
    const controller = requestRef.current;
    if (!controller || controller.signal.aborted || saving ||
        !skills.some((skill) => skill.skillId === skillId && skill.ownerId === userId)) return;
    const { signal } = controller;
    bindingChanges.current.add(skillId);
    setSaving(skillId);
    setEnableError(false);
    try {
      // 点击时重新读取，避免用页面加载时的 information 覆盖较新的个人资料。
      const latest = await getProfile(signal);
      if (signal.aborted) return;
      const merged = { ...latest, skills: Array.from(new Set([...latest.skills, skillId])) };
      const response = await fetchWithAuth(PROFILE_PATH, {
        method: "PUT", signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(merged),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const saved = readProfile(await response.json());
      if (!saved.skills.includes(skillId)) throw new Error("Binding not saved");
      if (signal.aborted) return;
      setProfile(saved);
      const value = await checkCapability(skillId, signal);
      if (!signal.aborted) setAvailability((current) => ({ ...current, [skillId]: value }));
    } catch {
      if (!signal.aborted) setEnableError(true);
    } finally {
      if (!signal.aborted) setSaving(null);
    }
  }

  const needle = query.trim().toLocaleLowerCase();
  const visible = skills.filter((skill) =>
    (section !== "mine" || skill.ownerId === userId) &&
    [skill.displayName, skill.name, skill.description].some((value) => value?.toLocaleLowerCase().includes(needle)),
  );
  const needsRetry = !checking && skills.some((skill) => !availability[skill.skillId] || availability[skill.skillId] === "unknown");

  return (
    <main className="page-container min-h-full text-foreground">
      <div className="page-body">
        <header className="page-header page-header--compact">
          <div>
            <h1 className="page-header__title">{zh ? "能力中心" : "Capability center"}</h1>
          </div>
          {studioEnabled && <Link href="/skills/studio/new" className="button-primary text-sm"><Plus className="h-4 w-4" aria-hidden="true" />{zh ? "新建技能" : "Create skill"}</Link>}
        </header>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-2" role="group" aria-label={zh ? "能力筛选" : "Capability filter"}>
            <button type="button" aria-pressed={section === "all"} className={section === "all" ? "button-primary text-sm" : "button-secondary text-sm"} onClick={() => setSection("all")}>{zh ? "发现能力" : "Discover capabilities"}</button>
            <button type="button" aria-pressed={section === "mine"} className={section === "mine" ? "button-primary text-sm" : "button-secondary text-sm"} onClick={() => setSection("mine")}>{zh ? "我的技能" : "My skills"}</button>
          </div>
          <label className="relative w-full sm:w-72">
            <span className="sr-only">{zh ? "搜索技能" : "Search skills"}</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} className="glass-control w-full py-2 pl-9 pr-3 text-sm" placeholder={zh ? "搜索名称或描述…" : "Search name or description…"} />
          </label>
        </div>
        <details className="mb-3 text-xs text-muted-foreground"><summary className="cursor-pointer py-2">{zh ? "能力使用说明" : "Using capabilities"}</summary><p className="pb-2">{zh ? "此处保留所有对你可见的共享资源。可见不代表已绑定或可调用；开始前需服务端确认。点击开始使用会进入对话并携带能力提示，不会自动发送消息。" : "All resources shared with you remain discoverable. Visibility does not imply callable access; the server confirms it. Starting opens a chat with a capability hint, without sending a message."}</p></details>
        {!isLoading && !error && <p className="mb-4 text-xs text-muted-foreground" role="status">{zh ? `${visible.length} 项技能` : `${visible.length} skills`}{checking && (zh ? " · 正在确认可用性…" : " · Checking availability…")}</p>}
        {(error || profileFailed || needsRetry) && <div role="alert" className="notice notice--danger mb-4 flex flex-wrap items-center justify-between gap-3">
          <span>{error ? (zh ? "技能加载失败。" : "Could not load skills.") : profileFailed ? (zh ? "个人启用状态未知；暂时无法为我启用。" : "Personal bindings are unknown; enabling is unavailable.") : (zh ? "部分能力状态未知，暂不能开始。" : "Some capabilities have unknown access and cannot be started.")}</span>
          <button type="button" className="button-secondary text-sm" disabled={saving !== null} onClick={retry}>{zh ? "重试" : "Retry"}</button>
        </div>}
        {enableError && <div role="alert" className="notice notice--danger mb-4">{zh ? "启用失败，未确认保存成功。请重试或刷新核对状态。" : "Enabling failed; saving was not confirmed. Retry or refresh to check the current state."}</div>}
        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" role="status">
            <span className="sr-only">{translate(locale, "common.loading")}</span>
            {[1, 2, 3].map((i) => <div key={i} className="skeleton h-56" aria-hidden="true" />)}
          </div>
        ) : error ? null : visible.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon"><Sparkles className="h-5 w-5" aria-hidden="true" /></span>
            <p className="empty-state__title">{needle ? (zh ? "没有匹配的技能" : "No matching skills") : section === "mine" ? (zh ? "你还没有自己的技能" : "No skills of your own yet") : (zh ? "暂无可见能力" : "No visible capabilities yet")}</p>
            {needle ? <button type="button" className="button-secondary mt-3 text-sm" onClick={() => setQuery("")}>{zh ? "清除搜索" : "Clear search"}</button> : studioEnabled && <Link href="/skills/studio/new" className="button-primary mt-3 text-sm">{zh ? "新建技能" : "Create skill"}</Link>}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {visible.map((skill) => {
              const own = skill.ownerId === userId;
              const platform = skill.ownerId === "aitana-platform";
              const enabled = own && !!profile?.skills.includes(skill.skillId);
              const status = availability[skill.skillId] ?? "unknown";
              return <article key={skill.skillId} className="glass-panel feature-card flex flex-col p-4" aria-label={skill.displayName || skill.name}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-xl border bg-[var(--brand-soft)] text-base font-semibold text-primary">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {skill.avatar ? <img src={skill.avatar} alt="" className="h-full w-full object-cover" /> : (skill.displayName || skill.name || "?").slice(0, 1).toUpperCase()}
                  </div>
                  <span className="text-xs text-muted-foreground">{own ? (zh ? "我的技能" : "My skill") : platform ? (zh ? "平台技能" : "Platform skill") : (zh ? "共享技能" : "Shared skill")}</span>
                </div>
                <h2 className="mt-3 break-words text-[15px] font-semibold">{skill.displayName || skill.name}</h2>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{skill.description}</p>
                <div className="my-3 space-y-1 text-xs" role="status">
                  <p className={status === "available" ? "text-primary" : "text-muted-foreground"}>{status === "available" ? (zh ? "可使用 · 服务端已确认绑定" : "Ready · Server-confirmed binding") : status === "unbound" ? (zh ? "未获得可调用绑定" : "No callable binding") : (zh ? "可用状态未知" : "Availability unknown")}</p>
                  {enabled && <p>{zh ? "已为我启用" : "Enabled for me"}</p>}
                  {status !== "available" && <p className="text-muted-foreground">{own && !enabled ? (zh ? "下一步：为我启用；仍不可用时请管理员配置。" : "Next: enable for yourself; ask an administrator if access remains unavailable.") : (zh ? "下一步：请管理员检查 Agent 绑定与访问配置。" : "Next: ask an administrator to check Agent bindings and access.")}</p>}
                </div>
                <div className="mt-auto flex flex-wrap items-center gap-2 border-t pt-3">
                  {status === "available" ? <Link href={`/chat/${encodeURIComponent(skill.skillId)}`} prefetch={false} className="button-primary text-sm">{zh ? "开始使用" : "Start using"}<ArrowUpRight className="h-4 w-4" aria-hidden="true" /></Link> : <button type="button" className="button-primary text-sm disabled:opacity-50" disabled>{zh ? "开始使用" : "Start using"}</button>}
                  {own && profile && !enabled && <button type="button" className="button-secondary text-sm disabled:opacity-50" disabled={saving !== null} onClick={() => void enableForMe(skill.skillId)}>{saving === skill.skillId ? (zh ? "正在启用…" : "Enabling…") : (zh ? "为我启用" : "Enable for me")}</button>}
                  {own && studioEnabled && <Link href={`/skills/studio/${encodeURIComponent(skill.skillId)}`} className="button-secondary text-sm">{zh ? "编辑" : "Edit"}</Link>}
                  {!own && platform && studioEnabled && <Link href={`/skills/studio/${encodeURIComponent(skill.skillId)}`} className="button-secondary text-sm">{zh ? "在 Studio 中创建副本" : "Fork in Studio"}</Link>}
                </div>
              </article>;
            })}
          </div>
        )}
      </div>
    </main>
  );
}
