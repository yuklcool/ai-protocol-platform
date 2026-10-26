"use client";

import NextLink from "next/link";
import { AgentReadiness } from "@/components/admin/AgentReadiness";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import type { TranslationKey } from "@/lib/i18n";

type Link = {
  href: string;
  label: TranslationKey;
  note?: TranslationKey;
};

type Area = {
  href: string;
  title: TranslationKey;
  question: TranslationKey;
  links: Link[];
  platformOnly?: boolean;
};

const AREAS: Area[] = [
  {
    href: "/agent",
    title: "admin.area.agent.title",
    question: "admin.area.agent.question",
    links: [
      {
        href: "/agent",
        label: "admin.area.agent.settings",
        note: "admin.area.agent.settingsNote",
      },
    ],
  },
  {
    href: "/admin/users",
    title: "admin.area.people.title",
    question: "admin.area.people.question",
    links: [
      {
        href: "/admin/users",
        label: "admin.area.people.users",
        note: "admin.area.people.usersNote",
      },
    ],
  },
  {
    href: "/skills",
    title: "admin.area.skills.title",
    question: "admin.area.skills.question",
    links: [
      {
        href: "/skills",
        label: "admin.area.skills.studio",
        note: "admin.area.skills.studioNote",
      },
      {
        // Keep old bookmarks and the explicit Skill authoring workflow
        // reachable while the main product path is Root Agent-first.
        href: "/skills/studio/new",
        label: "admin.area.skills.studioLegacy",
        note: "admin.area.skills.studioNote",
      },
      {
        href: "/admin/mcp-servers",
        label: "admin.area.skills.mcp",
        note: "admin.area.skills.mcpNote",
      },
    ],
  },
  {
    href: "/admin/analytics",
    title: "admin.area.activity.title",
    question: "admin.area.activity.question",
    links: [
      {
        href: "/admin/analytics",
        label: "admin.area.activity.sessions",
        note: "admin.area.activity.sessionsNote",
      },
      {
        href: "/admin/audit",
        label: "admin.area.activity.audit",
        note: "admin.area.activity.auditNote",
      },
    ],
  },
  {
    href: "/admin/settings",
    title: "admin.area.platform.title",
    question: "admin.area.platform.question",
    links: [
      {
        href: "/admin/model-providers",
        label: "admin.area.platform.models",
        note: "admin.area.platform.modelsNote",
      },
      {
        href: "/admin/settings",
        label: "admin.area.platform.settings",
        note: "admin.area.platform.settingsNote",
      },
    ],
    platformOnly: true,
  },
];

export default function AdminHub() {
  const { t, locale } = useI18n();
  const studioEnabled = process.env.NEXT_PUBLIC_ENABLE_SKILL_STUDIO === "true";
  const { user, loading } = useAuth();
  const { state, isAdmin, isPlatform, recheck } = useAdminScope(
    !loading && !!user,
  );

  if (loading || state === "loading")
    return <Centered><div role="status" className="skeleton w-full max-w-md p-6 text-center text-sm text-muted-foreground">{t("admin.loading")}</div></Centered>;
  if (!user) return <SignInRequired />;

  if (state === "error") {
    return (
      <Centered>
        <div className="glass-panel max-w-md p-6 text-center">
          <h1 className="notice notice--danger mb-2 text-lg font-semibold">
            {t("admin.accessCheckFailed")}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t("admin.accessConnectionProblem")}
          </p>
          <button
            type="button"
            onClick={() => void recheck()}
            className="button-secondary mt-3 px-3 py-1.5 text-sm"
          >
            {t("admin.recheck")}
          </button>
        </div>
      </Centered>
    );
  }

  if (!isAdmin) {
    return (
      <Centered>
        <div className="glass-panel max-w-md p-6 text-center">
          <h1 className="mb-2 text-lg font-semibold">{t("admin.only")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("admin.onlyDescription")}
          </p>
          <p className="mt-3 text-sm text-muted-foreground">
            {t("admin.justGranted")}
          </p>
          <button
            type="button"
            onClick={() => void recheck()}
            className="button-secondary mt-2 px-3 py-1.5 text-sm"
          >
            {t("admin.recheck")}
          </button>
        </div>
      </Centered>
    );
  }

  const areas = AREAS.filter((area) => isPlatform || !area.platformOnly);

  return (
    <main className="page-container mx-auto max-w-4xl">
      <header className="page-header">
        <div className="min-w-0">
          <h1 className="page-header__title">{t("admin.title")}</h1>
          <p className="page-header__desc">{t("admin.subtitle")}</p>
        </div>
        <div className="page-header__actions">
          <NextLink href="/chat/root-agent" className="button-secondary px-3 py-2 text-sm">
            {locale === "zh-CN" ? "返回对话" : "Back to chat"}
          </NextLink>
        </div>
      </header>
      <div className="page-body">
        <section className="glass-panel mb-5 flex flex-wrap items-center justify-between gap-4 p-5"><div><h2>{locale === "zh-CN" ? "让助手准备就绪" : "Get your assistant ready"}</h2><p className="mt-1 text-sm text-muted-foreground">{locale === "zh-CN" ? "按步骤完成模型接入、能力配置与验证。" : "Connect a model, configure capabilities and verify the setup."}</p></div><NextLink href="/setup" className="button-primary">{locale === "zh-CN" ? "打开配置向导" : "Open setup guide"}</NextLink></section>
        <div className="grid gap-4 sm:grid-cols-2">
          {areas.map((area) => (
            <section key={area.title} className="glass-panel min-w-0 p-5">
              <h2 className="font-medium">{t(area.title)}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {t(area.question)}
              </p>
              <ul className="mt-3 space-y-1.5">
                {area.links
                  .filter((link) => studioEnabled || link.href !== "/skills/studio/new")
                  .map((link) => (
                    <li key={link.label}>
                      <NextLink
                        href={link.href}
                        className="inline-flex rounded-md px-2 py-1 text-sm font-medium text-primary transition-colors hover:bg-primary/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                      >
                        {t(link.label)}
                      </NextLink>
                      {link.note && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {t(link.note)}
                        </span>
                      )}
                    </li>
                  ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="mt-5"><AgentReadiness key={user.uid} /></div>
      </div>
    </main>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <main className="page-container flex min-h-[100dvh] items-center justify-center p-8">
      {children}
    </main>
  );
}
