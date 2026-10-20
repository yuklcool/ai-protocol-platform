"use client";

import Link from "next/link";
import { useI18n } from "@/contexts/I18nContext";
import { skillHref } from "@/components/navigation/skillHref";
import { SkillStatusBadge } from "@/components/skills/SkillStatusBadge";

export interface MarketplaceSkillSummary {
  skillId: string;
  ownerId: string;
  slug: string | null;
  name: string;
  displayName?: string;
  description: string;
  tags?: string[];
}

export function MarketplaceSkillsSection({
  skills,
}: {
  skills: MarketplaceSkillSummary[];
}) {
  const { t } = useI18n();
  if (skills.length === 0) return null;

  return (
    <section className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-8 md:py-16">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-base font-semibold">
          {t("home.skills")}
        </h2>
        <span className="badge px-3 py-1 text-xs text-muted-foreground">
          {t("home.skillsAvailable", { count: skills.length })}
        </span>
      </div>
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {skills.map((skill) => (
          <li key={skill.skillId} className="min-w-0">
            <Link
              href={skillHref(skill)}
              className="glass-panel glass-panel--flat group flex h-full min-w-0 flex-col gap-3 p-5 transition-colors hover:border-primary/30 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 sm:p-6"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="min-w-0 break-words text-base font-semibold text-foreground group-hover:text-primary">
                  {skill.displayName || skill.name}
                </span>
                <SkillStatusBadge tags={skill.tags} />
              </div>
              {skill.description && (
                <span className="line-clamp-2 break-words text-sm leading-relaxed text-muted-foreground">
                  {skill.description}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
