"use client";

import Link from "next/link";
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
      <main className="page-container p-8 text-sm text-muted-foreground">
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
  return (
    <main className="page-container min-h-full text-foreground">
      <header className="border-b px-5 py-5 sm:px-8">
        <p className="text-xs text-muted-foreground">
          {t("resources.skills.title")}
        </p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              {t("resources.skills.title")}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("resources.skills.subtitle")}
            </p>
          </div>
          <Link
            href="/skills/studio/new"
            className="button-primary px-3 py-2 text-xs font-medium "
          >
            {t("resources.skills.new")}
          </Link>
        </div>
      </header>
      <div className="mx-auto max-w-5xl p-5 sm:p-8">
        {error && (
          <div className="mb-4 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </div>
        )}
        {isLoading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-32 animate-pulse glass-panel bg-muted/40"
              />
            ))}
          </div>
        ) : skills.length === 0 ? (
          <div className="glass-panel border-dashed p-10 text-center text-sm text-muted-foreground">
            {t("resources.skills.empty")}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {skills.map((skill) => (
              <Link
                key={skill.skillId}
                href={`/skills/studio/${encodeURIComponent(skill.skillId)}`}
                className="glass-panel feature-card relative p-4 transition hover:border-primary/60 hover:bg-accent/30"
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted text-sm font-semibold">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {skill.avatar ? (
                      <img
                        src={skill.avatar}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      (skill.displayName || skill.name || "?")
                        .slice(0, 1)
                        .toUpperCase()
                    )}
                  </div>
                  <div className="min-w-0">
                    <h2 className="truncate text-sm font-semibold">
                      {skill.displayName || skill.name}
                    </h2>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                      {skill.description}
                    </p>
                  </div>
                </div>
                <div className="mt-4 text-[11px] text-muted-foreground">
                  {t("resources.skills.content")}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
