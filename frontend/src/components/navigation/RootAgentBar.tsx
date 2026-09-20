"use client";

import Link from "next/link";
import { Bot, Settings2, SquarePen } from "lucide-react";
import { useRouter } from "next/navigation";
import type { Skill } from "@/types/skill";
import { skillHref } from "./skillHref";
import { useI18n } from "@/contexts/I18nContext";
import { translate } from "@/lib/i18n";
import { UserMenu } from "./UserMenu";
import { BRANDING } from "@/lib/branding";

export function RootAgentBar({
  skills,
  defaultSkill,
  currentSkillId,
}: {
  skills: Skill[];
  defaultSkill?: Skill;
  currentSkillId: string;
}) {
  const router = useRouter();
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  return <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-card/70 px-4" aria-label="Root Agent navigation">
    <Link href="/" className="flex shrink-0 items-center" aria-label="Home">{/* eslint-disable-next-line @next/next/no-img-element */}<img src={BRANDING.logo.chatAvatar} alt={BRANDING.appName} className="h-8 w-8 rounded-full" /></Link>
    <div className="flex min-w-0 items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary"><Bot className="h-4 w-4" aria-hidden /></span><div className="min-w-0"><p className="truncate text-sm font-medium">{t("rootAgent.title")}</p><p className="truncate text-[11px] text-muted-foreground">{t("rootAgent.bar.capabilities")}</p></div></div>
    <Link href="/skills" className="hidden rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground sm:inline-flex">{t("rootAgent.bar.skills")}</Link>
    <div className="flex-1" />
    <button type="button" onClick={() => { const target = defaultSkill ?? skills.find((s) => s.skillId === currentSkillId) ?? skills[0]; if (target) router.push(skillHref(target)); }} disabled={skills.length === 0} className="flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"><SquarePen className="h-4 w-4" aria-hidden /><span className="hidden sm:inline">{t("rootAgent.bar.newChat")}</span></button>
    <Link href="/agent" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border text-muted-foreground hover:bg-muted hover:text-foreground" title={t("rootAgent.bar.configure")} aria-label={t("rootAgent.bar.configure")}><Settings2 className="h-4 w-4" aria-hidden /></Link>
    <UserMenu />
  </header>;
}
