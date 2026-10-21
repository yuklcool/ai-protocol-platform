"use client";

import Link from "next/link";
import { Bot, Settings2, SquarePen } from "lucide-react";
import { useRouter } from "next/navigation";
import type { Skill } from "@/types/skill";
import { useI18n } from "@/contexts/I18nContext";
import { translate } from "@/lib/i18n";
import { UserMenu } from "./UserMenu";
import { BRANDING } from "@/lib/branding";
import { useAdminScope } from "@/hooks/useAdminScope";

export function RootAgentBar({}: {
  skills: Skill[];
  defaultSkill?: Skill;
  currentSkillId: string;
}) {
  const router = useRouter();
  const scope = useAdminScope();
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translate>[1]) => translate(locale, key);
  return (
    <header
      className="app-toolbar flex min-h-14 shrink-0 items-center gap-2 px-3 sm:gap-3 sm:px-5"
      aria-label="Root Agent navigation"
    >
      <Link
        href="/workspace"
        className="flex shrink-0 items-center"
        aria-label={locale.startsWith("zh") ? "返回工作台" : "Back to workspace"}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={BRANDING.logo.chatAvatar}
          alt={BRANDING.appName}
          className="h-8 w-8 rounded-xl"
        />
      </Link>
      <div className="flex min-w-0 items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Bot className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{t("rootAgent.title")}</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {t("rootAgent.bar.capabilities")}
          </p>
        </div>
      </div>
      <Link
        href="/skills"
        className="button-ghost hidden text-xs sm:inline-flex"
      >
        {t("rootAgent.bar.skills")}
      </Link>
      <div className="flex-1" />
      <button
        type="button"
        onClick={() => {
          router.push("/chat/root-agent");
        }}
        className="button-secondary min-h-10 shrink-0 text-xs disabled:opacity-50"
        aria-label={t("rootAgent.bar.newChat")}
      >
        <SquarePen className="h-4 w-4" aria-hidden />
        <span className="hidden sm:inline">{t("rootAgent.bar.newChat")}</span>
      </button>
      {scope.isPlatform && (
        <Link
          href="/agent"
          className="button-ghost h-10 w-10 shrink-0 p-0"
          title={t("rootAgent.bar.configure")}
          aria-label={t("rootAgent.bar.configure")}
        >
          <Settings2 className="h-4 w-4" aria-hidden />
        </Link>
      )}
      <UserMenu />
    </header>
  );
}
