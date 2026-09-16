"use client";

import { useEffect, useMemo, useState } from "react";
import NextLink from "next/link";

import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { fetchWithAuth } from "@/lib/apiClient";
import {
  translateMcpAdmin,
  type McpAdminTranslationKey,
} from "@/lib/i18n/mcpAdmin";

type Scope = "platform" | "tenant";
type Transport = "http" | "streamable-http" | "sse";
type PageTranslator = (
  key: McpAdminTranslationKey,
  params?: Record<string, string | number>,
) => string;

type McpServer = {
  server_id: string;
  url: string;
  transport: Transport | string;
  scope: Scope | string;
  tenant_id: string | null;
  enabled: boolean;
  description: string;
  header_names: string[];
  has_credentials: boolean;
};

type McpHealth = {
  ok: boolean;
  category?: string | null;
  message?: string | null;
  server?: Record<string, unknown> | null;
};

type McpDiscovery = McpHealth & {
  tools: Array<Record<string, unknown>>;
  resources: Array<Record<string, unknown>>;
  prompts: Array<Record<string, unknown>>;
  warnings: Array<{ capability: string; category: string; message: string }>;
  mcp_apps: { supported: boolean; resourceUris: string[] };
};

type Skill = {
  skillId: string;
  name: string;
  displayName?: string;
  skillMetadata?: Record<string, unknown>;
};

type FormState = {
  serverId: string;
  url: string;
  transport: Transport;
  scope: Scope;
  tenantId: string;
  enabled: boolean;
  description: string;
  headersText: string;
  clearHeaders: boolean;
};

const API = "/api/proxy/api/admin/mcp-servers";
const SKILLS_API = "/api/proxy/api/skills";

function emptyForm(isPlatform: boolean, tenantId = ""): FormState {
  return {
    serverId: "",
    url: "",
    transport: "streamable-http",
    scope: isPlatform ? "platform" : "tenant",
    tenantId,
    enabled: true,
    description: "",
    headersText: "",
    clearHeaders: false,
  };
}

function parseHeaders(raw: string, t: PageTranslator): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) throw new Error(t("headers.invalidLine", { line: trimmed }));
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (!key) throw new Error(t("headers.emptyName"));
    result[key] = value;
  }
  return result;
}

function mcpServersForSkill(skill: Skill): string[] {
  const metadata = (skill.skillMetadata ?? {}) as Record<string, unknown>;
  const toolConfigs = (metadata.toolConfigs ?? {}) as Record<string, unknown>;
  const mcp = (toolConfigs.mcp ?? {}) as Record<string, unknown>;
  return Array.isArray(mcp.servers) ? mcp.servers.map(String) : [];
}

function withMcpServer(skill: Skill, serverId: string, bind: boolean): Record<string, unknown> {
  const metadata = { ...((skill.skillMetadata ?? {}) as Record<string, unknown>) };
  const toolConfigs = { ...((metadata.toolConfigs ?? {}) as Record<string, unknown>) };
  const mcp = { ...((toolConfigs.mcp ?? {}) as Record<string, unknown>) };
  const current = Array.isArray(mcp.servers) ? mcp.servers.map(String) : [];
  mcp.servers = bind
    ? Array.from(new Set([...current, serverId]))
    : current.filter((id) => id !== serverId);
  toolConfigs.mcp = mcp;
  metadata.toolConfigs = toolConfigs;
  return metadata;
}

async function errorDetail(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return fallback;
}

export default function McpServersPage() {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  const { state, domains, isAdmin, isPlatform } = useAdminScope(!loading && !!user);
  const defaultTenant = domains[0] ?? "";

  const [servers, setServers] = useState<McpServer[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [form, setForm] = useState<FormState>(() => emptyForm(false));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [diagnosticId, setDiagnosticId] = useState<string | null>(null);
  const [health, setHealth] = useState<McpHealth | null>(null);
  const [discovery, setDiscovery] = useState<McpDiscovery | null>(null);
  const [selectedSkillId, setSelectedSkillId] = useState("");

  const t: PageTranslator = (key, params = {}) => translateMcpAdmin(locale, key, params);

  const boundSkills = useMemo(() => {
    if (!diagnosticId) return [];
    return skills.filter((skill) => mcpServersForSkill(skill).includes(diagnosticId));
  }, [diagnosticId, skills]);

  const load = async () => {
    setNotice(null);
    try {
      const [serversResponse, skillsResponse] = await Promise.all([
        fetchWithAuth(API),
        fetchWithAuth(`${SKILLS_API}?limit=200`),
      ]);
      if (!serversResponse.ok) {
        setNotice(await errorDetail(serversResponse, t("load.servers")));
        return;
      }
      if (!skillsResponse.ok) {
        setNotice(await errorDetail(skillsResponse, t("load.skills")));
        return;
      }
      setServers(await serversResponse.json());
      setSkills(await skillsResponse.json());
    } catch {
      setNotice(t("load.service"));
    }
  };

  useEffect(() => {
    if (loading || !user || !isAdmin) return;
    setForm(emptyForm(isPlatform, defaultTenant));
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user, isAdmin, isPlatform, defaultTenant, locale]);

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm(isPlatform, defaultTenant));
  };

  const edit = (server: McpServer) => {
    setEditingId(server.server_id);
    setForm({
      serverId: server.server_id,
      url: server.url,
      transport: server.transport === "sse" ? "sse" : server.transport === "http" ? "http" : "streamable-http",
      scope: server.scope === "platform" ? "platform" : "tenant",
      tenantId: server.tenant_id ?? defaultTenant,
      enabled: server.enabled,
      description: server.description ?? "",
      headersText: "",
      clearHeaders: false,
    });
  };

  const save = async () => {
    const id = form.serverId.trim();
    if (!id || !form.url.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      const body: Record<string, unknown> = {
        url: form.url.trim(),
        transport: form.transport,
        scope: isPlatform ? form.scope : "tenant",
        tenant_id: isPlatform && form.scope === "tenant" ? form.tenantId.trim() || null : undefined,
        enabled: form.enabled,
        description: form.description.trim(),
      };
      if (form.clearHeaders) body.headers = {};
      else if (form.headersText.trim()) body.headers = parseHeaders(form.headersText, t);

      const response = await fetchWithAuth(`${API}/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        setNotice(await errorDetail(response, t("save.failed", { id })));
        return;
      }
      setNotice(t("save.ok", { id }));
      resetForm();
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : t("save.failed", { id }));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (server: McpServer) => {
    if (
      typeof window !== "undefined" &&
      !window.confirm(t("delete.confirm", { id: server.server_id }))
    ) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetchWithAuth(`${API}/${encodeURIComponent(server.server_id)}`, { method: "DELETE" });
      if (!response.ok) {
        setNotice(await errorDetail(response, t("delete.failed", { id: server.server_id })));
        return;
      }
      if (diagnosticId === server.server_id) {
        setDiagnosticId(null);
        setHealth(null);
        setDiscovery(null);
      }
      setNotice(t("delete.ok", { id: server.server_id }));
      await load();
    } finally {
      setBusy(false);
    }
  };

  const toggleEnabled = async (server: McpServer) => {
    setBusy(true);
    setNotice(null);
    const body: Record<string, unknown> = {
      url: server.url,
      transport: server.transport,
      scope: server.scope,
      tenant_id: server.tenant_id,
      enabled: !server.enabled,
      description: server.description,
      // headers intentionally omitted: backend preserves write-only credentials.
    };
    try {
      const response = await fetchWithAuth(`${API}/${encodeURIComponent(server.server_id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        setNotice(
          await errorDetail(
            response,
            t("toggle.failed", {
              action: server.enabled ? t("action.disable") : t("action.enable"),
              id: server.server_id,
            }),
          ),
        );
        return;
      }
      setNotice(
        t(server.enabled ? "toggle.disabled" : "toggle.enabled", { id: server.server_id }),
      );
      await load();
    } finally {
      setBusy(false);
    }
  };

  const runHealth = async (server: McpServer) => {
    setDiagnosticId(server.server_id);
    setHealth(null);
    setDiscovery(null);
    setNotice(null);
    const response = await fetchWithAuth(`${API}/${encodeURIComponent(server.server_id)}/health`, { method: "POST" });
    if (!response.ok) {
      setNotice(await errorDetail(response, t("health.failed", { id: server.server_id })));
      return;
    }
    setHealth(await response.json());
  };

  const runDiscovery = async (server: McpServer) => {
    setDiagnosticId(server.server_id);
    setHealth(null);
    setDiscovery(null);
    setNotice(null);
    const response = await fetchWithAuth(`${API}/${encodeURIComponent(server.server_id)}/discover`, { method: "POST" });
    if (!response.ok) {
      setNotice(await errorDetail(response, t("discovery.failed", { id: server.server_id })));
      return;
    }
    setDiscovery(await response.json());
  };

  const updateBinding = async (bind: boolean) => {
    if (!diagnosticId || !selectedSkillId) return;
    const skill = skills.find((item) => item.skillId === selectedSkillId);
    if (!skill) return;
    const skillName = skill.displayName || skill.name;
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetchWithAuth(`${SKILLS_API}/${encodeURIComponent(skill.skillId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skillMetadata: withMcpServer(skill, diagnosticId, bind) }),
      });
      if (!response.ok) {
        setNotice(
          await errorDetail(
            response,
            t(bind ? "binding.failedBind" : "binding.failedUnbind", {
              server: diagnosticId,
              skill: skillName,
            }),
          ),
        );
        return;
      }
      setNotice(
        t(bind ? "binding.bound" : "binding.unbound", {
          server: diagnosticId,
          skill: skillName,
        }),
      );
      await load();
    } finally {
      setBusy(false);
    }
  };

  if (loading || state === "loading") return <Centered>{t("state.loading")}</Centered>;
  if (!user) return <SignInRequired />;
  if (state === "error") return <Centered>{t("state.adminUnavailable")}</Centered>;
  if (!isAdmin) return <Centered>{t("state.adminRequired")}</Centered>;

  return (
    <main className="mx-auto max-w-6xl p-6">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{t("title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("description")}</p>
          {!isPlatform && domains.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("scoped", { domains: domains.join(", ") })}
            </p>
          )}
        </div>
        <NextLink href="/admin" className="rounded-md border px-3 py-1.5 text-sm hover:bg-muted/40">
          {t("back")}
        </NextLink>
      </header>

      {notice && <div className="mb-4 rounded-md border px-3 py-2 text-sm">{notice}</div>}

      <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <section className="rounded-lg border">
          <div className="border-b px-4 py-3">
            <h2 className="font-medium">{t("registry.title")}</h2>
            <p className="text-xs text-muted-foreground">{t("registry.description")}</p>
          </div>
          {servers.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              {t("registry.empty")}
            </p>
          ) : (
            <div className="divide-y">
              {servers.map((server) => (
                <article key={server.server_id} className="p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-medium">{server.server_id}</span>
                        <Badge>
                          {server.scope === "platform"
                            ? t("form.platform")
                            : server.scope === "tenant"
                              ? t("form.tenant")
                              : server.scope}
                        </Badge>
                        <Badge>{server.transport}</Badge>
                        <Badge>{server.enabled ? t("registry.enabled") : t("registry.disabled")}</Badge>
                        {server.has_credentials && <Badge>{t("registry.credentials")}</Badge>}
                      </div>
                      <p className="mt-1 break-all text-xs text-muted-foreground">{server.url}</p>
                      {server.tenant_id && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {t("registry.tenant", { tenant: server.tenant_id })}
                        </p>
                      )}
                      {server.description && <p className="mt-2 text-sm">{server.description}</p>}
                      {server.header_names.length > 0 && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {t("registry.headers", { headers: server.header_names.join(", ") })}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <Action onClick={() => void runHealth(server)}>{t("action.health")}</Action>
                      <Action onClick={() => void runDiscovery(server)}>{t("action.discover")}</Action>
                      <Action onClick={() => void toggleEnabled(server)} disabled={busy}>
                        {server.enabled ? t("action.disable") : t("action.enable")}
                      </Action>
                      <Action onClick={() => edit(server)}>{t("action.edit")}</Action>
                      <Action danger onClick={() => void remove(server)} disabled={busy}>
                        {t("action.delete")}
                      </Action>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-lg border p-4">
          <h2 className="font-medium">
            {editingId ? t("form.editTitle", { id: editingId }) : t("form.addTitle")}
          </h2>
          <div className="mt-3 grid gap-3">
            <Field label={t("form.serverId")}>
              <input
                className="w-full rounded-md border px-3 py-2 text-sm font-mono disabled:opacity-60"
                value={form.serverId}
                disabled={!!editingId}
                placeholder="example-map"
                onChange={(event) => setForm({ ...form, serverId: event.target.value })}
              />
            </Field>
            <Field label={t("form.url")}>
              <input
                className="w-full rounded-md border px-3 py-2 text-sm font-mono"
                value={form.url}
                placeholder="http://mcp-example-map:8080/mcp"
                onChange={(event) => setForm({ ...form, url: event.target.value })}
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("form.transport")}>
                <select
                  className="w-full rounded-md border px-3 py-2 text-sm"
                  value={form.transport}
                  onChange={(event) => setForm({ ...form, transport: event.target.value as Transport })}
                >
                  <option value="streamable-http">Streamable HTTP</option>
                  <option value="http">HTTP</option>
                  <option value="sse">SSE</option>
                </select>
              </Field>
              <Field label={t("form.scope")}>
                <select
                  className="w-full rounded-md border px-3 py-2 text-sm"
                  value={isPlatform ? form.scope : "tenant"}
                  disabled={!isPlatform}
                  onChange={(event) => setForm({ ...form, scope: event.target.value as Scope })}
                >
                  <option value="tenant">{t("form.tenant")}</option>
                  {isPlatform && <option value="platform">{t("form.platform")}</option>}
                </select>
              </Field>
            </div>
            {isPlatform && form.scope === "tenant" && (
              <Field label={t("form.tenantId")}>
                <input
                  className="w-full rounded-md border px-3 py-2 text-sm font-mono"
                  value={form.tenantId}
                  onChange={(event) => setForm({ ...form, tenantId: event.target.value })}
                />
              </Field>
            )}
            <Field label={t("form.description")}>
              <input
                className="w-full rounded-md border px-3 py-2 text-sm"
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </Field>
            <Field label={t("form.credentialHeaders")}>
              <textarea
                className="min-h-24 w-full rounded-md border px-3 py-2 text-sm font-mono"
                value={form.headersText}
                onChange={(event) => setForm({ ...form, headersText: event.target.value, clearHeaders: false })}
                placeholder={'Authorization=${MCP_TOKEN}\nX-Api-Key=${MCP_API_KEY}'}
              />
              <p className="mt-1 text-xs text-muted-foreground">{t("form.headersHelp")}</p>
              {editingId && (
                <label className="mt-2 flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={form.clearHeaders}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        clearHeaders: event.target.checked,
                        headersText: event.target.checked ? "" : form.headersText,
                      })
                    }
                  />
                  {t("form.clearHeaders")}
                </label>
              )}
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
              />
              {t("form.enabled")}
            </label>
            <div className="flex justify-end gap-2">
              <button
                className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted/40"
                onClick={resetForm}
                disabled={busy}
              >
                {t("form.clear")}
              </button>
              <button
                className="rounded-md border px-3 py-2 text-sm hover:bg-muted/40 disabled:opacity-50"
                onClick={() => void save()}
                disabled={busy || !form.serverId.trim() || !form.url.trim()}
              >
                {busy ? t("form.saving") : t("form.save")}
              </button>
            </div>
          </div>
        </section>
      </div>

      {diagnosticId && (
        <section className="mt-6 rounded-lg border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-medium">
                {t("diagnostics.title")} · <span className="font-mono">{diagnosticId}</span>
              </h2>
              <p className="text-xs text-muted-foreground">{t("diagnostics.description")}</p>
            </div>
            <button
              className="text-xs text-muted-foreground underline"
              onClick={() => {
                setDiagnosticId(null);
                setHealth(null);
                setDiscovery(null);
              }}
            >
              {t("diagnostics.close")}
            </button>
          </div>
          {health && <DiagnosticStatus result={health} t={t} />}
          {discovery && (
            <div className="mt-3 space-y-3">
              <DiagnosticStatus result={discovery} t={t} />
              {discovery.ok && (
                <div className="grid gap-3 md:grid-cols-4">
                  <Count title={t("diagnostics.tools")} value={discovery.tools.length} />
                  <Count title={t("diagnostics.resources")} value={discovery.resources.length} />
                  <Count title={t("diagnostics.prompts")} value={discovery.prompts.length} />
                  <Count
                    title={t("diagnostics.apps")}
                    value={discovery.mcp_apps.supported ? discovery.mcp_apps.resourceUris.length : 0}
                  />
                </div>
              )}
              {discovery.mcp_apps.resourceUris.length > 0 && (
                <div className="rounded-md bg-muted/30 p-3 text-xs">
                  <div className="font-medium">{t("diagnostics.appUris")}</div>
                  {discovery.mcp_apps.resourceUris.map((uri) => (
                    <div key={uri} className="mt-1 break-all font-mono text-muted-foreground">
                      {uri}
                    </div>
                  ))}
                </div>
              )}
              {discovery.warnings.length > 0 && (
                <div className="rounded-md border border-amber-500/40 p-3 text-xs">
                  {discovery.warnings.map((warning, index) => (
                    <p key={`${warning.capability}-${index}`}>
                      <strong>{warning.capability}</strong> · {warning.category}: {warning.message}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="mt-5 border-t pt-4">
            <h3 className="text-sm font-medium">{t("binding.title")}</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("binding.description")}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <select
                className="min-w-64 rounded-md border px-3 py-2 text-sm"
                value={selectedSkillId}
                onChange={(event) => setSelectedSkillId(event.target.value)}
              >
                <option value="">{t("binding.select")}</option>
                {skills.map((skill) => (
                  <option key={skill.skillId} value={skill.skillId}>
                    {skill.displayName || skill.name}
                  </option>
                ))}
              </select>
              <Action onClick={() => void updateBinding(true)} disabled={busy || !selectedSkillId}>
                {t("binding.bind")}
              </Action>
              <Action onClick={() => void updateBinding(false)} disabled={busy || !selectedSkillId}>
                {t("binding.unbind")}
              </Action>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {t("binding.current", {
                skills: boundSkills.length
                  ? boundSkills.map((skill) => skill.displayName || skill.name).join(", ")
                  : t("binding.none"),
              })}
            </p>
          </div>
        </section>
      )}
    </main>
  );
}

function DiagnosticStatus({ result, t }: { result: McpHealth; t: PageTranslator }) {
  return (
    <div
      className={`mt-3 rounded-md border p-3 text-sm ${
        result.ok ? "border-emerald-500/40" : "border-red-500/40"
      }`}
    >
      <strong>
        {result.ok
          ? t("diagnostics.connected")
          : t("diagnostics.failed", {
              category: result.category || t("diagnostics.unknown"),
            })}
      </strong>
      {result.message && (
        <p className="mt-1 break-words text-xs text-muted-foreground">{result.message}</p>
      )}
    </div>
  );
}

function Count({ title, value }: { title: string; value: number }) {
  return (
    <div className="rounded-md bg-muted/30 p-3">
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
      {children}
    </span>
  );
}

function Action({
  children,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md border px-2 py-1 text-xs hover:bg-muted/40 disabled:opacity-50 ${
        danger ? "text-red-600" : ""
      }`}
    >
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="text-xs text-muted-foreground">
      <span className="mb-1 block">{label}</span>
      {children}
    </label>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>;
}
