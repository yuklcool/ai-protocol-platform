"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, Plus, Search, Sparkles } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { useUserSkills } from "@/hooks/useUserSkills";
import { translate } from "@/lib/i18n";

export default function SkillsResourcePage() {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  const t = (
    key: Parameters<typeof translate>[1],
    params?: Parameters<typeof translate>[2],
  ) => translate(locale, key, params);
  if (loading)
    return (
      <main className="page-container text-sm text-muted-foreground" role="status">
        {translate(locale, "common.loading")}
      </main>
    );
  if (!user) return <SignInRequired />;
  return <SkillsResourceInner userId={user.uid} t={t} />;
}

function SkillsResourceInner({
  userId,
  t,
}: {
  userId: string;
  t: (
    key: Parameters<typeof translate>[1],
    params?: Parameters<typeof translate>[2],
  ) => string;
}) {
  const { skills, isLoading, error } = useUserSkills(userId);
  const { locale } = useI18n();
  const zh = locale.startsWith("zh");
  const [query, setQuery] = useState("");
  const needle = query.trim().toLocaleLowerCase();
  const visible = skills.filter((skill) =>
    [skill.displayName, skill.name, skill.description]
      .some((value) => value?.toLocaleLowerCase().includes(needle)),
  );
  return (
    <main className="page-container min-h-full text-foreground">
      <div className="page-body">
        <header className="page-header">
          <div>
            <p className="page-header__eyebrow">{zh ? "能力资源" : "Resources"}</p>
            <h1 className="page-header__title">{t("resources.skills.title")}</h1>
            <p className="page-header__desc">{t("resources.skills.subtitle")}</p>
          </div>
          <Link href="/skills/studio/new" className="button-primary text-sm">
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t("resources.skills.new")}
          </Link>
        </header>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground" role="status">
            {!isLoading && !error && (zh ? `${visible.length} 项技能` : `${visible.length} skills`)}
          </p>
          <label className="relative w-full sm:w-72">
            <span className="sr-only">{zh ? "搜索技能" : "Search skills"}</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <input type="search" value={query} onChange={(event) => setQuery(event.target.value)}
              className="glass-control w-full py-2 pl-9 pr-3 text-sm"
              placeholder={zh ? "搜索名称或描述…" : "Search name or description…"} />
          </label>
        </div>
        {error && <div role="alert" className="notice notice--danger mb-4">{error}</div>}
        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" role="status">
            <span className="sr-only">{t("common.loading")}</span>
            {[1, 2, 3].map((i) => <div key={i} className="skeleton h-40" aria-hidden="true" />)}
          </div>
        ) : error && skills.length === 0 ? null : visible.length === 0 ? (
          <div className="empty-state">
            <span className="empty-state__icon"><Sparkles className="h-5 w-5" aria-hidden="true" /></span>
            <p className="empty-state__title">{needle ? (zh ? "没有匹配的技能" : "No matching skills") : t("resources.skills.empty")}</p>
            {needle ? <button type="button" className="button-secondary mt-3 text-sm" onClick={() => setQuery("")}>{zh ? "清除搜索" : "Clear search"}</button> :
              <Link href="/skills/studio/new" className="button-primary mt-3 text-sm">{t("resources.skills.new")}</Link>}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {visible.map((skill) => (
              <Link key={skill.skillId} href={`/skills/studio/${encodeURIComponent(skill.skillId)}`}
                className="glass-panel feature-card group flex flex-col p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-xl border bg-[var(--brand-soft)] text-base font-semibold text-primary">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {skill.avatar ? <img src={skill.avatar} alt="" className="h-full w-full object-cover" /> :
                      (skill.displayName || skill.name || "?").slice(0, 1).toUpperCase()}
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-muted-foreground group-hover:text-primary" aria-hidden="true" />
                </div>
                <h2 className="mt-4 truncate text-[15px] font-semibold">{skill.displayName || skill.name}</h2>
                <p className="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">{skill.description}</p>
                <div className="mt-4 border-t pt-3 text-[11px] text-muted-foreground">{t("resources.skills.content")}</div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
