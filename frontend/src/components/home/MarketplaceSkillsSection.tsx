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
    <section className="mx-auto w-full max-w-7xl px-6 py-16 md:px-10">
      <div className="mb-6 flex items-end justify-between">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          {t("home.skills")}
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          {t("home.skillsAvailable", { count: skills.length })}
        </span>
      </div>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {skills.map((skill) => (
          <li key={skill.skillId}>
            <Link
              href={skillHref(skill)}
              className="group flex h-full flex-col gap-2 rounded-lg border border-border bg-background p-4 transition-colors hover:border-primary/50 hover:bg-muted/40"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="text-sm font-semibold text-foreground group-hover:text-primary">
                  {skill.displayName || skill.name}
                </span>
                <SkillStatusBadge tags={skill.tags} />
              </div>
              {skill.description && (
                <span className="line-clamp-2 text-xs text-muted-foreground">
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
