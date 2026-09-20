"use client";

import Link from "next/link";
import { Bot, ChevronRight, CirclePlus, LayoutDashboard, Settings2, SlidersHorizontal } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useUserSkills } from "@/hooks/useUserSkills";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { translate } from "@/lib/i18n";
import type { Skill } from "@/types/skill";

export function AgentListPage() {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  if (loading) return <div className="p-8 text-sm text-muted-foreground">{translate(locale, "common.loading")}</div>;
  if (!user) return <SignInRequired />;
  return <AgentList userId={user.uid} />;
}

function AgentList({ userId }: { userId: string }) {
  const { locale } = useI18n();
  const { skills, isLoading, error } = useUserSkills(userId);
  const t = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate(locale, key, params);
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="hidden w-60 shrink-0 border-r bg-card/60 p-3 md:block">
        <Link href="/" className="flex items-center gap-2 px-2 py-3 text-sm font-semibold"><Bot className="h-5 w-5 text-primary" aria-hidden />AI Protocol Platform</Link>
        <nav className="mt-6 space-y-1" aria-label="Application navigation">
          <NavItem href="/" icon={<LayoutDashboard className="h-4 w-4" />} label={t("agents.nav.overview")} />
          <NavItem href="/agents" active icon={<Bot className="h-4 w-4" />} label={t("agents.nav.agents")} />
          <p className="px-2 pb-1 pt-6 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{t("agents.nav.resources")}</p>
          <NavItem href="/admin/mcp-servers" icon={<SlidersHorizontal className="h-4 w-4" />} label={t("agents.nav.mcp")} />
          <p className="px-2 pb-1 pt-6 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{t("agents.nav.settings")}</p>
          <NavItem href="/admin" icon={<Settings2 className="h-4 w-4" />} label={t("agents.nav.settings")} />
        </nav>
      </aside>
      <main className="min-w-0 flex-1">
        <header className="flex h-14 items-center justify-between border-b px-5 sm:px-8">
          <div><p className="text-xs text-muted-foreground">{t("agents.breadcrumb")}</p><h1 className="text-base font-semibold">{t("agents.title")}</h1></div>
          <Link href="/agents/new" className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground"><CirclePlus className="h-4 w-4" aria-hidden />{t("agents.create")}</Link>
        </header>
        <div className="mx-auto max-w-6xl p-5 sm:p-8">
          <div className="mb-6 flex items-end justify-between gap-4"><div><h2 className="text-2xl font-semibold tracking-tight">{t("agents.heading")}</h2><p className="mt-1 text-sm text-muted-foreground">{t("agents.description")}</p></div><span className="text-xs text-muted-foreground">{t("agents.count", { count: skills.length })}</span></div>
          {error && <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
          {isLoading ? <AgentGridSkeleton /> : skills.length === 0 ? <EmptyAgents /> : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{skills.map((skill) => <AgentCard key={skill.skillId} skill={skill} />)}</div>}
        </div>
      </main>
    </div>
  );
}

function AgentCard({ skill }: { skill: Skill }) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate(locale, key, params);
  return <Link href={`/agents/${encodeURIComponent(skill.skillId)}`} className="group rounded-lg border bg-card p-4 transition hover:border-primary/60 hover:bg-accent/30">
    <div className="flex items-start gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg border bg-muted">{skill.avatar ? <img src={skill.avatar} alt="" className="h-full w-full object-cover" /> : <Bot className="h-5 w-5 text-muted-foreground" aria-hidden />}</div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><h3 className="truncate text-sm font-semibold">{skill.displayName || skill.name}</h3><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" title={t("agents.status.active")} /></div><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{skill.description || t("agents.noDescription")}</p></div><ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden /></div>
    <div className="mt-4 flex items-center gap-2 text-[11px] text-muted-foreground"><span className="rounded border px-1.5 py-0.5">{skill.skillMetadata?.category || t("agents.category.default")}</span><span>·</span><span>{skill.skillMetadata?.tools?.length ?? 0} {t("agents.tools")}</span></div>
  </Link>;
}

function NavItem({ href, label, icon, active = false }: { href: string; label: string; icon: React.ReactNode; active?: boolean }) { return <Link href={href} className={`flex items-center gap-2 rounded-md px-2.5 py-2 text-sm ${active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>{icon}{label}</Link>; }
function AgentGridSkeleton() { return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[1,2,3].map((i) => <div key={i} className="h-32 animate-pulse rounded-lg border bg-muted/40" />)}</div>; }
function EmptyAgents() { const { locale } = useI18n(); return <div className="rounded-lg border border-dashed p-10 text-center"><Bot className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden /><h3 className="mt-3 text-sm font-semibold">{translate(locale, "agents.emptyTitle")}</h3><p className="mt-1 text-xs text-muted-foreground">{translate(locale, "agents.emptyDescription")}</p><Link href="/agents/new" className="mt-4 inline-flex rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground">{translate(locale, "agents.create")}</Link></div>; }

