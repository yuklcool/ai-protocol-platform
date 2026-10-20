"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Save, Sparkles } from "lucide-react";
import { useI18n } from "@/contexts/I18nContext";
import { translateSkillStudio } from "@/lib/i18n/skillStudio";
import type { StudioDraft } from "./draft";

export function SkillStudioShell({ draft, isNew, isDirty, isSaving, onSave, onCancel, children }: {
  draft: StudioDraft; isNew: boolean; isDirty: boolean; isSaving: boolean;
  onSave: () => void; onCancel: () => void; children: ReactNode;
}) {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translateSkillStudio>[1]) => translateSkillStudio(locale, key);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="app-toolbar flex shrink-0 flex-wrap items-center gap-3 px-4 py-3">
        <Sparkles className="h-5 w-5 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <Link href="/skills" className="inline-flex min-h-11 items-center text-xs text-muted-foreground hover:text-primary">{t("studio.agentStudio")}</Link>
          <h1 className="truncate text-sm font-semibold">{isNew ? t("studio.newSkill") : draft.displayName || draft.name}</h1>
        </div>
        <span className={`badge hidden sm:inline-flex ${isDirty ? "badge--warning" : "badge--success"}`}>{isDirty ? t("studio.unsaved") : t("studio.synced")}</span>
        <button type="button" onClick={onCancel} className="button-secondary min-h-11 px-3 py-1.5 text-xs">{t("studio.cancel")}</button>
        <button type="button" onClick={onSave} disabled={!isDirty || isSaving} className="button-primary min-h-11 items-center gap-1.5 px-3 py-1.5 text-xs disabled:opacity-50">
          <Save className="h-3.5 w-3.5" aria-hidden />{isSaving ? t("studio.saving") : t("studio.save")}
        </button>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto"><div className="mx-auto max-w-3xl p-4 sm:p-6">{children}</div></main>
    </div>
  );
}
