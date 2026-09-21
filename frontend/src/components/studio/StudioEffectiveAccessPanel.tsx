"use client";

import { AlertTriangle, BookOpen, CheckCircle2, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { translateSkillStudio, type SkillStudioTranslationKey } from "@/lib/i18n/skillStudio";
import type { StudioDraft } from "@/components/studio/applyProposal";

interface EffectiveAccessResponse {
  skill: { skillId: string; label: string };
  viewer: { tenantId: string; domain: string };
  gates: {
    skillAccess: boolean;
    tenantVisibility: boolean;
    rootBinding: boolean;
    reason: string;
  };
  capabilities: {
    skillTools: string[];
    rootTools: string[];
    effectiveTools: string[];
    skillMcpServers: string[];
    rootMcpServers: string[];
    effectiveMcpServers: string[];
    rootKnowledge: string[];
  };
  knowledge: { folderPath: string; tenantScoped: boolean };
}

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: EffectiveAccessResponse };

export function StudioEffectiveAccessPanel({
  draft,
  isDirty,
}: {
  draft: StudioDraft;
  isDirty: boolean;
}) {
  const { locale } = useI18n();
  const t = (key: SkillStudioTranslationKey) => translateSkillStudio(locale, key);
  const skillId = draft.skillId;
  const [state, setState] = useState<State>({ kind: "idle" });

  useEffect(() => {
    if (!skillId) {
      setState({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setState({ kind: "loading" });
    fetchWithAuth(`/api/proxy/api/skills/${encodeURIComponent(skillId)}/effective-access`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return (await response.json()) as EffectiveAccessResponse;
      })
      .then((data) => {
        if (!cancelled) setState({ kind: "ready", data });
      })
      .catch((error) => {
        if (!cancelled) setState({ kind: "error", message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [skillId]);

  const localFolder = draft.welcome?.bucketBrowser?.rootPath?.trim() || "—";
  const localTools = draft.skillMetadata?.tools ?? [];
  const localMcp = Array.isArray(draft.skillMetadata?.toolConfigs?.mcp?.servers)
    ? draft.skillMetadata?.toolConfigs?.mcp?.servers.map(String)
    : [];

  return (
    <div className="mt-4 rounded-lg border bg-background p-4">
      <div className="flex items-center gap-2 text-xs font-medium">
        <ShieldCheck className="h-3.5 w-3.5 text-primary" aria-hidden />
        {t("effective.title")}
      </div>
      <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{t("effective.description")}</p>

      {isDirty && skillId && (
        <p className="mt-3 flex items-start gap-2 rounded border border-amber-500/30 bg-amber-500/5 px-2.5 py-2 text-[11px] leading-4 text-amber-700 dark:text-amber-500">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          {t("effective.savedOnly")}
        </p>
      )}

      {!skillId && (
        <div className="mt-3 space-y-2 text-[11px] text-muted-foreground">
          <p>{t("effective.saveFirst")}</p>
          <LocalResourceSummary tools={localTools} mcp={localMcp} folder={localFolder} t={t} />
        </div>
      )}

      {state.kind === "loading" && <p className="mt-3 inline-flex items-center gap-2 text-[11px] text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" aria-hidden />{t("effective.loading")}</p>}
      {state.kind === "error" && <p className="mt-3 text-[11px] text-destructive">{t("effective.failed")} ({state.message})</p>}
      {state.kind === "ready" && <EffectiveResult data={state.data} t={t} />}
    </div>
  );
}

function EffectiveResult({ data, t }: { data: EffectiveAccessResponse; t: (key: SkillStudioTranslationKey) => string }) {
  const { gates, capabilities, knowledge, viewer } = data;
  return (
    <div className="mt-3 space-y-3 text-[11px]">
      <div className="grid grid-cols-3 gap-1.5">
        <Gate label={t("effective.skillAccess")} allowed={gates.skillAccess} />
        <Gate label={t("effective.tenantAccess")} allowed={gates.tenantVisibility} />
        <Gate label={t("effective.rootBinding")} allowed={gates.rootBinding} />
      </div>
      <p className="text-muted-foreground">{gates.reason}</p>
      <div className="space-y-1 border-t pt-2">
        <ResourceLine label={t("effective.tools")} value={capabilities.effectiveTools.join(", ") || "—"} />
        <ResourceLine label={t("effective.mcp")} value={capabilities.effectiveMcpServers.join(", ") || "—"} />
        <ResourceLine label={t("effective.knowledge")} value={capabilities.rootKnowledge.join(", ") || "—"} />
        <ResourceLine label={t("effective.folder")} value={knowledge.folderPath || "—"} />
        <ResourceLine label={t("effective.tenant")} value={viewer.tenantId || viewer.domain || "—"} />
      </div>
      <p className="flex items-start gap-2 text-muted-foreground"><BookOpen className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />{knowledge.tenantScoped ? t("effective.knowledgeScoped") : t("effective.knowledgeUnavailable")}</p>
    </div>
  );
}

function LocalResourceSummary({ tools, mcp, folder, t }: { tools: string[]; mcp: string[]; folder: string; t: (key: SkillStudioTranslationKey) => string }) {
  return <div className="space-y-1"><ResourceLine label={t("effective.tools")} value={tools.join(", ") || "—"} /><ResourceLine label={t("effective.mcp")} value={mcp.join(", ") || "—"} /><ResourceLine label={t("effective.folder")} value={folder} /></div>;
}

function Gate({ label, allowed }: { label: string; allowed: boolean }) {
  return <span className={`inline-flex min-w-0 items-center justify-center gap-1 rounded px-1.5 py-1 ${allowed ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-500" : "bg-destructive/10 text-destructive"}`}><span className="truncate">{label}</span>{allowed ? <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden /> : <XCircle className="h-3 w-3 shrink-0" aria-hidden />}</span>;
}

function ResourceLine({ label, value }: { label: string; value: string }) {
  return <div className="flex items-start justify-between gap-2"><span className="text-muted-foreground">{label}</span><span className="max-w-[190px] truncate text-right font-mono">{value}</span></div>;
}
