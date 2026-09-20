"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Bot, Check, ChevronRight, CircleAlert, Loader2, Save } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { fetchWithAuth } from "@/lib/apiClient";
import { translate } from "@/lib/i18n";
import type { Skill } from "@/types/skill";
import {
  DEFAULT_ROOT_AGENT_CONFIG,
  normalizeRootAgentConfig,
  type RootAgentConfig,
} from "@/types/rootAgent";

type ToolInfo = { name: string; label?: string; description?: string; category?: string };
type McpServer = { server_id: string; enabled?: boolean; transport?: string; scope?: string; description?: string };
type ModelInfo = { id?: string; name?: string; label?: string };

const sections = [
  "overview", "model", "prompt", "skills", "tools", "mcp", "knowledge", "interaction", "permissions", "advanced",
] as const;
type Section = (typeof sections)[number];

const endpoint = "/api/proxy/api/admin/platform-config";

export function RootAgentSettingsPage() {
  const { user, loading } = useAuth();
  if (loading) return <Centered><Loader2 className="h-4 w-4 animate-spin" /></Centered>;
  if (!user) return <SignInRequired />;
  return <RootAgentSettingsInner />;
}

function RootAgentSettingsInner() {
  const { locale } = useI18n();
  const t = (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => translate(locale, key, params);
  const [config, setConfig] = useState<RootAgentConfig>(DEFAULT_ROOT_AGENT_CONFIG);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [servers, setServers] = useState<McpServer[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [section, setSection] = useState<Section>("overview");
  const [loadingData, setLoadingData] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [platformResponse, skillsResponse, toolsResponse, mcpResponse, modelsResponse] = await Promise.all([
          fetchWithAuth(endpoint),
          fetchWithAuth("/api/proxy/api/skills"),
          fetchWithAuth("/api/proxy/api/tools"),
          fetchWithAuth("/api/proxy/api/admin/mcp-servers"),
          fetchWithAuth("/api/proxy/api/models"),
        ]);
        if (platformResponse.status === 403) {
          if (!cancelled) setForbidden(true);
          return;
        }
        if (!platformResponse.ok) throw new Error(`HTTP ${platformResponse.status}`);
        const platform = await platformResponse.json() as { agent?: unknown };
        const skillData = skillsResponse.ok ? await skillsResponse.json() as unknown : [];
        const toolData = toolsResponse.ok ? await toolsResponse.json() as { tools?: ToolInfo[] } : {};
        const mcpData = mcpResponse.ok ? await mcpResponse.json() as unknown : [];
        const modelData = modelsResponse.ok ? await modelsResponse.json() as { models?: ModelInfo[] } : {};
        if (!cancelled) {
          setConfig(normalizeRootAgentConfig(platform.agent));
          setSkills(Array.isArray(skillData) ? skillData : []);
          setTools(Array.isArray(toolData.tools) ? toolData.tools : []);
          setServers(Array.isArray(mcpData) ? mcpData : []);
          setModels(Array.isArray(modelData.models) ? modelData.models : []);
        }
      } catch {
        if (!cancelled) setLoadError(true);
      } finally {
        if (!cancelled) setLoadingData(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const selectedSkills = useMemo(() => new Set(config.skills), [config.skills]);
  const selectedTools = useMemo(() => new Set(config.tools), [config.tools]);
  const selectedMcp = useMemo(() => new Set(config.mcpServers), [config.mcpServers]);
  const setPatch = (patch: Partial<RootAgentConfig>) => setConfig((current) => ({ ...current, ...patch }));
  const toggle = (key: "skills" | "tools" | "mcpServers", value: string, checked: boolean) => {
    setConfig((current) => {
      const values = new Set(current[key]);
      if (checked) values.add(value); else values.delete(value);
      return { ...current, [key]: [...values] };
    });
  };

  const save = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const response = await fetchWithAuth(endpoint, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: config }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const saved = await response.json() as { agent?: unknown };
      setConfig(normalizeRootAgentConfig(saved.agent ?? config));
      setNotice(t("rootAgent.saved"));
    } catch {
      setNotice(t("rootAgent.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  if (forbidden) return <Centered><p className="max-w-md text-center text-sm text-muted-foreground">{t("rootAgent.adminOnly")}</p></Centered>;
  if (loadingData) return <Centered><Loader2 className="h-4 w-4 animate-spin" /></Centered>;
  if (loadError) return <Centered><p className="text-sm text-destructive">{t("rootAgent.loadFailed")}</p></Centered>;

  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/15 text-primary"><Bot className="h-4 w-4" aria-hidden /></div>
        <div className="min-w-0"><div className="flex items-center gap-2 text-xs text-muted-foreground"><span>{t("rootAgent.breadcrumb")}</span><ChevronRight className="h-3 w-3" aria-hidden /><span className="truncate">{config.displayName}</span></div><h1 className="truncate text-sm font-semibold">{t("rootAgent.title")}</h1></div>
        <div className="flex-1" />
        {notice && <span className="text-xs text-muted-foreground">{notice}</span>}
        <button type="button" onClick={() => void save()} disabled={saving} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"><Save className="h-3.5 w-3.5" aria-hidden />{saving ? t("rootAgent.saving") : t("rootAgent.save")}</button>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[220px_minmax(0,1fr)_300px]">
        <aside className="hidden min-h-0 overflow-y-auto border-r bg-card/40 px-3 py-4 xl:block"><p className="mb-3 px-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{t("rootAgent.title")}</p><nav className="space-y-0.5" aria-label={t("rootAgent.title")}>{sections.map((id) => <button key={id} type="button" onClick={() => setSection(id)} className={`flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm ${section === id ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}><span>{t(`rootAgent.nav.${id}` as Parameters<typeof translate>[1])}</span><ChevronRight className="h-3.5 w-3.5" aria-hidden /></button>)}</nav><div className="mt-8 border-t pt-4"><Link href="/skills" className="block rounded-md px-2.5 py-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">{t("resources.skills.title")}</Link></div></aside>
        <main className="min-h-0 overflow-y-auto"><div className="mx-auto max-w-3xl p-4 sm:p-6"><div className="mb-5"><h2 className="text-xl font-semibold tracking-tight">{t(`rootAgent.nav.${section}` as Parameters<typeof translate>[1])}</h2><p className="mt-1 text-sm text-muted-foreground">{t("rootAgent.subtitle")}</p></div>{renderSection(section, { config, setPatch, toggle, skills, tools, servers, models, selectedSkills, selectedTools, selectedMcp, t })}</div></main>
        <aside className="hidden min-h-0 overflow-y-auto border-l bg-card/40 p-4 xl:block"><div className="rounded-lg border bg-background p-4"><div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-full border bg-primary/10 text-primary"><Bot className="h-4 w-4" aria-hidden /></div><div className="min-w-0"><p className="truncate text-sm font-medium">{config.displayName}</p><p className="truncate text-xs text-muted-foreground">{config.description}</p></div></div><div className="mt-4 space-y-2 text-xs"><SummaryRow label={t("rootAgent.overview.activeCapabilities")} value={t("rootAgent.overview.capabilitySummary", { skills: config.skills.length, tools: config.tools.length, mcp: config.mcpServers.length })} /><SummaryRow label={t("rootAgent.model.label")} value={config.model} /><SummaryRow label={t("rootAgent.nav.interaction")} value={config.interaction.a2uiEnabled ? "A2UI" : "Text"} /></div></div><div className="mt-4 rounded-lg border border-dashed bg-background/50 p-4 text-xs leading-5 text-muted-foreground">{t("rootAgent.compatibility")}</div></aside>
      </div>
    </div>
  );
}

type RenderContext = {
  config: RootAgentConfig;
  setPatch: (patch: Partial<RootAgentConfig>) => void;
  toggle: (key: "skills" | "tools" | "mcpServers", value: string, checked: boolean) => void;
  skills: Skill[];
  tools: ToolInfo[];
  servers: McpServer[];
  models: ModelInfo[];
  selectedSkills: Set<string>;
  selectedTools: Set<string>;
  selectedMcp: Set<string>;
  t: (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) => string;
};

function renderSection(section: Section, c: RenderContext) {
  const { config, setPatch, t } = c;
  const control = "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-ring";
  if (section === "overview") return <Card title={t("rootAgent.overview.identity")} hint={t("rootAgent.overview.identityHint")}><Field label={t("rootAgent.overview.displayName")}><input value={config.displayName} onChange={(e) => setPatch({ displayName: e.target.value })} className={control} /></Field><Field label={t("rootAgent.overview.description")}><input value={config.description} onChange={(e) => setPatch({ description: e.target.value })} className={control} /></Field></Card>;
  if (section === "model") return <Card title={t("rootAgent.model.label")} hint={t("rootAgent.model.hint")}><select aria-label={t("rootAgent.model.label")} value={config.model} onChange={(e) => setPatch({ model: e.target.value })} className={control}>{c.models.length ? c.models.map((model) => <option key={String(model.id ?? model.name)} value={String(model.id ?? model.name)}>{model.label ?? model.name ?? model.id}</option>) : ["smart", "pro", "lite"].map((model) => <option key={model} value={model}>{model}</option>)}</select></Card>;
  if (section === "prompt") return <Card title={t("rootAgent.prompt.label")} hint={t("rootAgent.prompt.hint")}><textarea aria-label={t("rootAgent.prompt.label")} value={config.instructions} onChange={(e) => setPatch({ instructions: e.target.value })} rows={14} className={`${control} font-mono`} /></Card>;
  if (section === "skills") return <ResourceChecklist title={t("rootAgent.skills.title")} description={t("rootAgent.skills.description")} empty={t("rootAgent.skills.empty")} items={c.skills.filter((skill) => skill.kind !== "system").map((skill) => ({ id: skill.skillId, label: skill.displayName || skill.name, detail: `${skill.kind === "development" ? "Development" : skill.kind === "specialist" ? "Specialist" : "Skill"} · ${skill.description}` }))} selected={c.selectedSkills} onToggle={(id, checked) => c.toggle("skills", id, checked)} />;
  if (section === "tools") return <ResourceChecklist title={t("rootAgent.tools.title")} description={t("rootAgent.tools.description")} empty={t("rootAgent.tools.empty")} items={c.tools.map((tool) => ({ id: tool.name, label: tool.label || tool.name, detail: tool.description }))} selected={c.selectedTools} onToggle={(id, checked) => c.toggle("tools", id, checked)} />;
  if (section === "mcp") return <ResourceChecklist title={t("rootAgent.mcp.title")} description={t("rootAgent.mcp.description")} empty={t("rootAgent.mcp.empty")} items={c.servers.map((server) => ({ id: server.server_id, label: server.server_id, detail: `${server.transport || "MCP"} · ${server.scope || "tenant"}${server.enabled === false ? " · disabled" : ""}`, disabled: server.enabled === false }))} selected={c.selectedMcp} onToggle={(id, checked) => c.toggle("mcpServers", id, checked)} />;
  if (section === "knowledge") return <Card title={t("rootAgent.knowledge.title")} hint={t("rootAgent.knowledge.description")}><textarea aria-label={t("rootAgent.knowledge.title")} value={config.knowledge.join("\n")} onChange={(e) => setPatch({ knowledge: e.target.value.split(/\n/).map((v) => v.trim()).filter(Boolean) })} placeholder={t("rootAgent.knowledge.placeholder")} rows={8} className={`${control} font-mono`} /></Card>;
  if (section === "interaction") return <Card title={t("rootAgent.interaction.title")}><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.interaction.a2uiEnabled} onChange={(e) => setPatch({ interaction: { ...config.interaction, a2uiEnabled: e.target.checked } })} />{t("rootAgent.interaction.a2ui")}</label><Field label={t("rootAgent.interaction.surface")}><select value={config.interaction.defaultSurface} onChange={(e) => setPatch({ interaction: { ...config.interaction, defaultSurface: e.target.value } })} className={control}><option value="chat">Chat</option><option value="workspace">Workspace</option><option value="sidebar">Sidebar</option><option value="modal">Dialog</option></select></Field><Field label={t("rootAgent.interaction.replace")}><select value={config.interaction.defaultUpdateMode} onChange={(e) => setPatch({ interaction: { ...config.interaction, defaultUpdateMode: e.target.value as "replace" | "patch" } })} className={control}><option value="replace">{t("rootAgent.interaction.replace")}</option><option value="patch">{t("rootAgent.interaction.patch")}</option></select></Field><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.interaction.allowSurfaceContextWrites} onChange={(e) => setPatch({ interaction: { ...config.interaction, allowSurfaceContextWrites: e.target.checked } })} />{t("rootAgent.interaction.context")}</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.interaction.allowActionTriggeredRuns} onChange={(e) => setPatch({ interaction: { ...config.interaction, allowActionTriggeredRuns: e.target.checked } })} />{t("rootAgent.interaction.actions")}</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.interaction.voiceEnabled} onChange={(e) => setPatch({ interaction: { ...config.interaction, voiceEnabled: e.target.checked } })} />{t("rootAgent.interaction.voice")}</label><Field label={t("rootAgent.interaction.welcome")}><textarea value={config.interaction.welcomeMessage} onChange={(e) => setPatch({ interaction: { ...config.interaction, welcomeMessage: e.target.value } })} rows={4} className={control} /></Field></Card>;
  if (section === "permissions") return <Card title={t("rootAgent.permissions.title")} hint={t("rootAgent.permissions.description")}><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.permissions.failClosed === true} onChange={(e) => setPatch({ permissions: { ...config.permissions, failClosed: e.target.checked } })} />{t("rootAgent.permissions.failClosed")}</label><div className="mt-3 flex items-start gap-2 rounded-md bg-primary/5 p-3 text-xs text-muted-foreground"><CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />{t("rootAgent.permissions.description")}</div></Card>;
  return <Card title={t("rootAgent.advanced.title")} hint={t("rootAgent.advanced.specialistsHint")}><Field label={t("rootAgent.advanced.specialists")}><textarea value={config.specialistAgents.join("\n")} onChange={(e) => setPatch({ specialistAgents: e.target.value.split(/\n/).map((v) => v.trim()).filter(Boolean) })} rows={6} className={`${control} font-mono`} /></Field><div className="mt-4 rounded-md border border-dashed p-3 text-xs text-muted-foreground">{t("rootAgent.advanced.legacy")}</div></Card>;
}

function Card({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) { return <section className="space-y-4 rounded-lg border bg-card/30 p-4"><div><h3 className="text-sm font-semibold">{title}</h3>{hint && <p className="mt-1 text-xs leading-5 text-muted-foreground">{hint}</p>}</div>{children}</section>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{label}</span>{children}</label>; }
function ResourceChecklist({ title, description, empty, items, selected, onToggle }: { title: string; description: string; empty: string; items: Array<{ id: string; label: string; detail?: string; disabled?: boolean }>; selected: Set<string>; onToggle: (id: string, checked: boolean) => void }) { return <Card title={title} hint={description}>{items.length === 0 ? <p className="text-xs text-muted-foreground">{empty}</p> : <div className="space-y-2">{items.map((item) => <label key={item.id} className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 ${selected.has(item.id) ? "border-primary/50 bg-primary/5" : "hover:bg-muted/40"}`}><input type="checkbox" className="mt-0.5" checked={selected.has(item.id)} disabled={item.disabled} onChange={(e) => onToggle(item.id, e.target.checked)} /><span className="min-w-0 flex-1"><span className="flex items-center gap-2 text-sm font-medium"><span className="truncate">{item.label}</span>{selected.has(item.id) && <Check className="h-3.5 w-3.5 text-emerald-500" aria-hidden />}</span>{item.detail && <span className="mt-0.5 block line-clamp-2 text-xs text-muted-foreground">{item.detail}</span>}</span></label>)}</div>}</Card>; }
function SummaryRow({ label, value }: { label: string; value: string }) { return <div className="flex items-center justify-between gap-3"><span className="text-muted-foreground">{label}</span><span className="max-w-[180px] truncate text-right font-mono text-[11px]">{value}</span></div>; }
function Centered({ children }: { children: React.ReactNode }) { return <main className="flex min-h-full items-center justify-center p-8">{children}</main>; }
