"use client";

import NextLink from "next/link";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
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
    href: "/admin/tenants",
    title: "admin.area.tenant.title",
    question: "admin.area.tenant.question",
    links: [
      {
        href: "/admin/tenants",
        label: "admin.area.tenant.config",
        note: "admin.area.tenant.configNote",
      },
      {
        href: "/admin/tenants",
        label: "admin.area.tenant.effective",
        note: "admin.area.tenant.effectiveNote",
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
      {
        href: "/admin/groups",
        label: "admin.area.people.groups",
        note: "admin.area.people.groupsNote",
      },
      {
        href: "/admin/tool-permissions",
        label: "admin.area.people.tools",
        note: "admin.area.people.toolsNote",
      },
    ],
  },
  {
    href: "/skills/studio/new",
    title: "admin.area.skills.title",
    question: "admin.area.skills.question",
    links: [
      {
        href: "/skills/studio/new",
        label: "admin.area.skills.studio",
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
  const { t } = useI18n();
  const { user, loading } = useAuth();
  const { state, domains, isAdmin, isPlatform, recheck } = useAdminScope(!loading && !!user);

  if (loading || state === "loading") return <Centered>{t("admin.loading")}</Centered>;
  if (!user) return <SignInRequired />;

  if (state === "error") {
    return (
      <Centered>
        <div className="max-w-md text-center">
          <h1 className="mb-2 text-lg font-semibold">{t("admin.accessCheckFailed")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("admin.accessConnectionProblem")}
          </p>
        </div>
      </Centered>
    );
  }

  if (!isAdmin) {
    return (
      <Centered>
        <div className="max-w-md text-center">
          <h1 className="mb-2 text-lg font-semibold">{t("admin.only")}</h1>
          <p className="text-sm text-muted-foreground">{t("admin.onlyDescription")}</p>
          <p className="mt-3 text-sm text-muted-foreground">{t("admin.justGranted")}</p>
          <button
            type="button"
            onClick={() => void recheck()}
            className="mt-2 rounded border px-3 py-1.5 text-sm hover:bg-muted"
          >
            {t("admin.recheck")}
          </button>
        </div>
      </Centered>
    );
  }

  const areas = AREAS.filter((area) => isPlatform || !area.platformOnly);

  return (
    <main className="mx-auto max-w-4xl p-6">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{t("admin.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("admin.subtitle")}</p>
          {!isPlatform && domains.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("admin.scopedTo", { domains: domains.join(", ") })}
            </p>
          )}
        </div>
        <LanguageSwitcher />
      </header>
      <div className="grid gap-4 sm:grid-cols-2">
        {areas.map((area) => (
          <section key={area.title} className="rounded-lg border p-4">
            <h2 className="font-medium">{t(area.title)}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t(area.question)}</p>
            <ul className="mt-3 space-y-1.5">
              {area.links.map((link) => (
                <li key={link.label}>
                  <NextLink
                    href={link.href}
                    className="text-sm text-foreground underline-offset-2 hover:underline"
                  >
                    {t(link.label)}
                  </NextLink>
                  {link.note && (
                    <span className="ml-2 text-xs text-muted-foreground">{t(link.note)}</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </main>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>;
}
