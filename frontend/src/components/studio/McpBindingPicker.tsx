"use client";

import { useEffect, useState } from "react";
import { Check, CircleAlert, Loader2, PlugZap } from "lucide-react";
import { fetchWithAuth } from "@/lib/apiClient";
import { useI18n } from "@/contexts/I18nContext";
import { translateSkillStudio, type SkillStudioTranslationKey } from "@/lib/i18n/skillStudio";
import type { StudioDraft } from "@/components/studio/applyProposal";

type McpServer = {
  server_id: string;
  transport?: string;
  scope?: string;
  enabled?: boolean;
  description?: string;
};

export function McpBindingPicker({ draft, setDraft }: {
  draft: StudioDraft;
  setDraft: React.Dispatch<React.SetStateAction<StudioDraft>>;
}) {
  const { locale } = useI18n();
  const t = (key: SkillStudioTranslationKey, params?: Record<string, string | number>) => translateSkillStudio(locale, key, params);
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const configured = draft.skillMetadata?.toolConfigs?.mcp;
  const selected = new Set(Array.isArray(configured?.servers) ? configured.servers.map(String) : []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchWithAuth("/api/proxy/api/admin/mcp-servers")
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return (await response.json()) as McpServer[];
      })
      .then((items) => { if (!cancelled) setServers(items); })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const toggle = (serverId: string, enabled: boolean) => {
    setDraft((previous) => {
      const metadata = previous.skillMetadata;
      const toolConfigs = { ...(metadata?.toolConfigs ?? {}) };
      const mcp = { ...(toolConfigs.mcp ?? {}) };
      const current = Array.isArray(mcp.servers) ? mcp.servers.map(String) : [];
      mcp.servers = enabled ? Array.from(new Set([...current, serverId])) : current.filter((id) => id !== serverId);
      toolConfigs.mcp = mcp;
      return { ...previous, skillMetadata: { ...metadata, toolConfigs } };
    });
  };

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2"><PlugZap className="h-4 w-4 text-primary" aria-hidden /><span className="text-sm font-medium">{t("mcpPicker.title")}</span></div>
        {!loading && <span className="text-xs text-muted-foreground">{t("mcpPicker.selected", { count: selected.size })}</span>}
      </div>
      <p className="text-xs text-muted-foreground">{t("mcpPicker.description")}</p>
      {loading && <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />{t("mcpPicker.loading")}</div>}
      {error && <div className="flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-700"><CircleAlert className="h-3.5 w-3.5" aria-hidden />{t("mcpPicker.unavailable", { error })}</div>}
      {!loading && !error && servers.length === 0 && <p className="text-xs text-muted-foreground">{t("mcpPicker.empty")}</p>}
      <div className="space-y-1.5">
        {servers.map((server) => {
          const checked = selected.has(server.server_id);
          return <label key={server.server_id} className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 transition ${checked ? "border-primary/50 bg-primary/5" : "hover:bg-muted/50"}`}>
            <input type="checkbox" className="mt-0.5" checked={checked} disabled={server.enabled === false} onChange={(event) => toggle(server.server_id, event.target.checked)} />
            <span className="min-w-0 flex-1"><span className="flex items-center gap-2 text-xs font-medium"><span className="truncate font-mono">{server.server_id}</span>{checked && <Check className="h-3.5 w-3.5 text-emerald-500" aria-hidden />}</span><span className="mt-0.5 flex flex-wrap gap-x-2 text-[11px] text-muted-foreground"><span>{server.transport || "MCP"}</span><span>{server.scope || "tenant"}</span>{server.enabled === false && <span className="text-amber-600">{t("mcpPicker.disabled")}</span>}</span>{server.description && <span className="mt-1 block line-clamp-2 text-[11px] text-muted-foreground">{server.description}</span>}</span>
          </label>;
        })}
      </div>
    </div>
  );
}

