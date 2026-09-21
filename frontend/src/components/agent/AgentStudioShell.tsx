"use client";

import { Bot, Check, ChevronRight, ExternalLink, Save, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { translateSkillStudio, type SkillStudioTranslationKey } from "@/lib/i18n/skillStudio";
import type { StudioDraft } from "@/components/studio/applyProposal";
import { StudioTestChat } from "@/components/studio/StudioTestChat";
import { StudioEffectiveAccessPanel } from "@/components/studio/StudioEffectiveAccessPanel";

const sections: Array<{ id: string; key: SkillStudioTranslationKey; detail?: string }> = [
  { id: "studio-overview", key: "studio.nav.overview" },
  { id: "studio-model", key: "studio.nav.model" },
  { id: "studio-prompt", key: "studio.nav.prompt" },
  { id: "studio-capabilities", key: "studio.nav.capabilities" },
  { id: "studio-knowledge", key: "studio.nav.knowledge" },
  { id: "studio-interaction", key: "studio.nav.interaction" },
  { id: "studio-permissions", key: "studio.nav.permissions" },
  { id: "studio-advanced", key: "studio.nav.advanced" },
];

export function SkillStudioShell({
  draft,
  isNew,
  isDirty,
  isSaving,
  onSave,
  onCancel,
  children,
}: {
  draft: StudioDraft;
  isNew: boolean;
  isDirty: boolean;
  isSaving: boolean;
  onSave: () => void;
  onCancel: () => void;
  children: ReactNode;
}) {
  const { locale } = useI18n();
  const t = (key: SkillStudioTranslationKey) => translateSkillStudio(locale, key);
  const name = draft.displayName || draft.name || t("studio.untitled");
  const model = draft.skillMetadata?.model || "smart";
  const tools = draft.skillMetadata?.tools ?? [];
  const mcp = draft.skillMetadata?.toolConfigs?.mcp;
  const mcpServers = Array.isArray(mcp?.servers) ? mcp.servers.map(String) : [];
  const hasA2ui = draft.skillMetadata?.toolConfigs?.a2ui !== undefined;

  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b bg-card px-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Bot className="h-4 w-4" aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{t("studio.agentStudio")}</span>
              <ChevronRight className="h-3 w-3" aria-hidden />
              <span className="truncate">{name}</span>
            </div>
            <h1 className="truncate text-sm font-semibold">{isNew ? t("studio.newSkill") : name}</h1>
          </div>
        </div>
        <div className="flex-1" />
        <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
          <span className={`h-1.5 w-1.5 rounded-full ${isDirty ? "bg-amber-500" : "bg-emerald-500"}`} />
          {isDirty ? t("studio.unsaved") : t("studio.synced")}
        </span>
        <button type="button" onClick={onCancel} className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted">
          {t("studio.cancel")}
        </button>
        <button type="button" onClick={onSave} disabled={!isDirty || isSaving}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50">
          <Save className="h-3.5 w-3.5" aria-hidden />
          {isSaving ? t("studio.saving") : t("studio.save")}
        </button>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[224px_minmax(0,1fr)_320px]">
        <aside className="hidden min-h-0 overflow-y-auto border-r bg-card/40 px-3 py-4 xl:block">
          <p className="mb-3 px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            {t("studio.configure")}
          </p>
          <nav aria-label={t("studio.configure")} className="space-y-0.5">
            {sections.map((section) => (
              <a key={section.id} href={`#${section.id}`}
                className="group flex items-center justify-between rounded-md px-2.5 py-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground">
                <span>{t(section.key)}</span>
                <ChevronRight className="h-3.5 w-3.5 opacity-0 transition group-hover:opacity-100" aria-hidden />
              </a>
            ))}
          </nav>
          <div className="mt-8 border-t pt-4">
            <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{t("studio.resources")}</p>
            <a href="/admin/mcp-servers" className="flex items-center gap-2 rounded-md px-2.5 py-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">
              <ExternalLink className="h-3.5 w-3.5" aria-hidden /> {t("studio.manageResources")}
            </a>
          </div>
        </aside>

        <main className="min-h-0 overflow-y-auto">
          <div className="mx-auto max-w-3xl p-4 sm:p-6">{children}</div>
        </main>

        <aside className="hidden min-h-0 flex-col border-l bg-card/40 xl:flex">
          <div className="border-b px-4 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-primary" aria-hidden />{t("studio.preview")}</div>
              <span className="rounded border px-1.5 py-0.5 text-[10px] text-muted-foreground">{t("studio.draft")}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{t("studio.previewDescription")}</p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <div className="rounded-lg border bg-background p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full border bg-muted">
                  {draft.persona?.avatar ? <img src={draft.persona.avatar} alt="" className="h-full w-full object-cover" /> : <Bot className="h-4 w-4 text-muted-foreground" aria-hidden />}
                </div>
                <div className="min-w-0"><p className="truncate text-sm font-medium">{name}</p><p className="text-xs text-muted-foreground">{draft.description || t("studio.noDescription")}</p></div>
              </div>
              <div className="mt-4 space-y-2 text-xs">
                <SummaryRow label={t("studio.model")} value={model} />
                <SummaryRow label={t("studio.tools")} value={String(tools.length)} />
                <SummaryRow label={t("studio.mcpServers")} value={String(mcpServers.length)} />
                <SummaryRow label="A2UI" value={hasA2ui ? t("studio.enabled") : t("studio.notConfigured")} />
              </div>
            </div>
            <StudioTestChat skillId={draft.skillId} isDirty={isDirty} />
            <StudioEffectiveAccessPanel draft={draft} isDirty={isDirty} />
            <div className="mt-4 flex items-start gap-2 rounded-lg bg-primary/5 p-3 text-xs leading-5 text-muted-foreground">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden />
              <span>{t("studio.compatibilityNotice")}</span>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

/** @deprecated Skills are edited in Skill Studio; keep this export for old imports. */
export const AgentStudioShell = SkillStudioShell;

function SummaryRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-3"><span className="text-muted-foreground">{label}</span><span className="max-w-[150px] truncate font-mono text-[11px]">{value}</span></div>;
}
