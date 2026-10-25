"use client";

import { useEffect, useRef, useState } from "react";
import NextLink from "next/link";

import { Notice } from "@/components/admin/ConsolePrimitives";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { fetchWithAuth } from "@/lib/apiClient";
import {
  translateMcpAdmin,
  type McpAdminTranslationKey,
} from "@/lib/i18n/mcpAdmin";

type Transport = "http" | "streamable-http" | "sse";
type PageTranslator = (
  key: McpAdminTranslationKey,
  params?: Record<string, string | number>,
) => string;

type McpServer = {
  server_id: string;
  url: string;
  transport: Transport | string;
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

type FormState = {
  serverId: string;
  url: string;
  transport: Transport;
  enabled: boolean;
  description: string;
  headersText: string;
  clearHeaders: boolean;
};

const API = "/api/proxy/api/admin/mcp-servers";

function emptyForm(): FormState {
  return {
    serverId: "",
    url: "",
    transport: "streamable-http",
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

async function errorDetail(
  response: Response,
  fallback: string,
): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return fallback;
}

export default function McpServersPage() {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  const { state, isAdmin } = useAdminScope(
    !loading && !!user,
  );

  const [servers, setServers] = useState<McpServer[]>([]);
  const [form, setForm] = useState<FormState>(() => emptyForm());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const formHeading = useRef<HTMLHeadingElement>(null);
  const formTrigger = useRef<HTMLButtonElement>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeTone, setNoticeTone] = useState<"info" | "success" | "danger">("info");
  const [serversLoading, setServersLoading] = useState(true);
  const [serversLoaded, setServersLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [diagnosticId, setDiagnosticId] = useState<string | null>(null);
  const [health, setHealth] = useState<McpHealth | null>(null);
  const [discovery, setDiscovery] = useState<McpDiscovery | null>(null);

  const t: PageTranslator = (key, params = {}) =>
    translateMcpAdmin(locale, key, params);

  useEffect(() => { if (formOpen) formHeading.current?.focus(); }, [formOpen, editingId]);

  const load = async () => {
    setServersLoading(true);
    setServersLoaded(false);
    setNotice(null);
    setNoticeTone("danger");
    try {
      const serversResponse = await fetchWithAuth(API);
      if (!serversResponse.ok) {
        setNotice(await errorDetail(serversResponse, t("load.servers")));
        return false;
      }
      setServers(await serversResponse.json());
      setServersLoaded(true);
      return true;
    } catch {
      setNotice(t("load.service"));
      return false;
    } finally {
      setServersLoading(false);
    }
  };

  useEffect(() => {
    if (loading || !user || !isAdmin) return;
    setForm(emptyForm());
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user, isAdmin, locale]);

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm());
  };

  const edit = (server: McpServer) => {
    setFormOpen(true);
    setEditingId(server.server_id);
    setForm({
      serverId: server.server_id,
      url: server.url,
      transport:
        server.transport === "sse"
          ? "sse"
          : server.transport === "http"
            ? "http"
            : "streamable-http",
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
    setNoticeTone("danger");
    try {
      const body: Record<string, unknown> = {
        url: form.url.trim(),
        transport: form.transport,
        enabled: form.enabled,
        description: form.description.trim(),
      };
      if (form.clearHeaders) body.headers = {};
      else if (form.headersText.trim())
        body.headers = parseHeaders(form.headersText, t);

      const response = await fetchWithAuth(`${API}/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        setNotice(await errorDetail(response, t("save.failed", { id })));
        return;
      }
      resetForm();
      const loaded = await load();
      if (loaded) {
        setNoticeTone("success");
        setNotice(t("save.ok", { id }));
      }
      setFormOpen(false);
      requestAnimationFrame(() => formTrigger.current?.focus());
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : t("save.failed", { id }),
      );
    } finally {
      setBusy(false);
    }
  };

  const remove = async (server: McpServer) => {
    if (
      typeof window !== "undefined" &&
      !window.confirm(t("delete.confirm", { id: server.server_id }))
    )
      return;
    setBusy(true);
    setNotice(null);
    setNoticeTone("danger");
    try {
      const response = await fetchWithAuth(
        `${API}/${encodeURIComponent(server.server_id)}`,
        { method: "DELETE" },
      );
      if (!response.ok) {
        setNotice(
          await errorDetail(
            response,
            t("delete.failed", { id: server.server_id }),
          ),
        );
        return;
      }
      if (diagnosticId === server.server_id) {
        setDiagnosticId(null);
        setHealth(null);
        setDiscovery(null);
      }
      setNoticeTone("success");
      setNotice(t("delete.ok", { id: server.server_id }));
      await load();
    } finally {
      setBusy(false);
    }
  };

  const toggleEnabled = async (server: McpServer) => {
    setBusy(true);
    setNotice(null);
    setNoticeTone("danger");
    const body: Record<string, unknown> = {
      url: server.url,
      transport: server.transport,
      enabled: !server.enabled,
      description: server.description,
      // headers intentionally omitted: backend preserves write-only credentials.
    };
    try {
      const response = await fetchWithAuth(
        `${API}/${encodeURIComponent(server.server_id)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
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
      setNoticeTone("success");
      setNotice(
        t(server.enabled ? "toggle.disabled" : "toggle.enabled", {
          id: server.server_id,
        }),
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
    setNoticeTone("danger");
    const response = await fetchWithAuth(
      `${API}/${encodeURIComponent(server.server_id)}/health`,
      { method: "POST" },
    );
    if (!response.ok) {
      setNotice(
        await errorDetail(
          response,
          t("health.failed", { id: server.server_id }),
        ),
      );
      return;
    }
    setHealth(await response.json());
  };

  const runDiscovery = async (server: McpServer) => {
    setDiagnosticId(server.server_id);
    setHealth(null);
    setDiscovery(null);
    setNotice(null);
    setNoticeTone("danger");
    const response = await fetchWithAuth(
      `${API}/${encodeURIComponent(server.server_id)}/discover`,
      { method: "POST" },
    );
    if (!response.ok) {
      setNotice(
        await errorDetail(
          response,
          t("discovery.failed", { id: server.server_id }),
        ),
      );
      return;
    }
    setDiscovery(await response.json());
  };

  if (loading || state === "loading")
    return <Centered><p role="status" className="skeleton w-full max-w-md p-6 text-center text-sm">{t("state.loading")}</p></Centered>;
  if (!user) return <SignInRequired />;
  if (state === "error")
    return <Centered><Notice tone="danger">{t("state.adminUnavailable")}</Notice></Centered>;
  if (!isAdmin) return <Centered><Notice tone="warning">{t("state.adminRequired")}</Notice></Centered>;

  return (
    <main className="page-container mx-auto max-w-6xl">
      <header className="page-header">
        <div className="min-w-0">
          <h1 className="page-header__title">{t("title")}</h1>
          <p className="page-header__desc">
            {t("description")}
          </p>
        </div>
        <div className="page-header__actions">
        <button ref={formTrigger} type="button" className="button-primary text-sm" aria-expanded={formOpen} aria-controls="mcp-server-form" onClick={() => { if (formOpen) { setFormOpen(false); resetForm(); } else { resetForm(); setFormOpen(true); } }} disabled={busy}>{t("form.addTitle")}</button>
        <NextLink
          href="/admin"
          className="button-secondary px-3 py-2 text-sm"
        >
          {t("back")}
        </NextLink>
        </div>
      </header>

      <div className="page-body space-y-5">
      <Notice tone={noticeTone}>{notice}</Notice>

      <div className={`grid items-start gap-4 ${formOpen ? "lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]" : ""}`}>
        <section className="glass-panel min-w-0 overflow-hidden">
          <div className="border-b px-4 py-3">
            <h2 className="font-medium">{t("registry.title")}</h2>
            <p className="text-xs text-muted-foreground">
              {t("registry.description")}
            </p>
          </div>
          {serversLoading ? (
            <p role="status" className="skeleton m-4 p-6 text-sm text-muted-foreground">{t("state.loading")}</p>
          ) : !serversLoaded && servers.length === 0 ? null : servers.length === 0 ? (
            <p className="empty-state text-sm text-muted-foreground">
              {t("registry.empty")}
            </p>
          ) : (
            <div className="divide-y">
              {servers.map((server) => (
                <article key={server.server_id} className="p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="break-all font-mono text-sm font-medium">
                          {server.server_id}
                        </span>
                        <Badge>{server.transport}</Badge>
                        <Badge tone={server.enabled ? "success" : "warning"}>
                          {server.enabled
                            ? t("registry.enabled")
                            : t("registry.disabled")}
                        </Badge>
                        {server.has_credentials && (
                          <Badge tone="brand">{t("registry.credentials")}</Badge>
                        )}
                      </div>
                      <p className="mt-1 break-all text-xs text-muted-foreground">
                        {server.url}
                      </p>
                      {server.description && (
                        <p className="mt-2 text-sm">{server.description}</p>
                      )}
                      {server.header_names.length > 0 && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {t("registry.headers", {
                            headers: server.header_names.join(", "),
                          })}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <Action onClick={() => void runHealth(server)}>
                        {t("action.health")}
                      </Action>
                      <Action onClick={() => void runDiscovery(server)}>
                        {t("action.discover")}
                      </Action>
                      <Action
                        onClick={() => void toggleEnabled(server)}
                        disabled={busy}
                      >
                        {server.enabled
                          ? t("action.disable")
                          : t("action.enable")}
                      </Action>
                      <Action onClick={() => edit(server)}>
                        {t("action.edit")}
                      </Action>
                      <Action
                        danger
                        onClick={() => void remove(server)}
                        disabled={busy}
                      >
                        {t("action.delete")}
                      </Action>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        {formOpen && <section id="mcp-server-form" className="glass-panel order-first min-w-0 p-4 lg:order-none">
          <div className="flex items-center justify-between gap-3"><h2 ref={formHeading} tabIndex={-1} className="font-medium">
            {editingId
              ? t("form.editTitle", { id: editingId })
              : t("form.addTitle")}
          </h2><button type="button" className="button-ghost text-xs" disabled={busy} onClick={() => { setFormOpen(false); resetForm(); formTrigger.current?.focus(); }}>{t("diagnostics.close")}</button></div>
          <div className="mt-3 grid gap-3">
            <Field label={t("form.serverId")}>
              <input
                className="glass-control w-full min-w-0 px-3 py-2 text-sm font-mono disabled:opacity-60"
                value={form.serverId}
                disabled={!!editingId}
                placeholder="example-map"
                onChange={(event) =>
                  setForm({ ...form, serverId: event.target.value })
                }
              />
            </Field>
            <Field label={t("form.url")}>
              <input
                className="glass-control w-full min-w-0 px-3 py-2 text-sm font-mono"
                value={form.url}
                placeholder="http://mcp-example-map:8080/mcp"
                onChange={(event) =>
                  setForm({ ...form, url: event.target.value })
                }
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("form.transport")}>
                <select
                  className="glass-control w-full min-w-0 px-3 py-2 text-sm"
                  value={form.transport}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      transport: event.target.value as Transport,
                    })
                  }
                >
                  <option value="streamable-http">Streamable HTTP</option>
                  <option value="http">HTTP</option>
                  <option value="sse">SSE</option>
                </select>
              </Field>
            </div>
            <Field label={t("form.description")}>
              <input
                className="glass-control w-full min-w-0 px-3 py-2 text-sm"
                value={form.description}
                onChange={(event) =>
                  setForm({ ...form, description: event.target.value })
                }
              />
            </Field>
            <Field label={t("form.credentialHeaders")}>
              <textarea
                className="min-h-24 glass-control w-full min-w-0 px-3 py-2 text-sm font-mono"
                value={form.headersText}
                onChange={(event) =>
                  setForm({
                    ...form,
                    headersText: event.target.value,
                    clearHeaders: false,
                  })
                }
                placeholder={
                  "Authorization=${MCP_TOKEN}\nX-Api-Key=${MCP_API_KEY}"
                }
              />
              <p className="mt-1 text-xs text-muted-foreground">
                {t("form.headersHelp")}
              </p>
              {editingId && (
                <label className="mt-2 flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={form.clearHeaders}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        clearHeaders: event.target.checked,
                        headersText: event.target.checked
                          ? ""
                          : form.headersText,
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
                onChange={(event) =>
                  setForm({ ...form, enabled: event.target.checked })
                }
              />
              {t("form.enabled")}
            </label>
            <div className="flex justify-end gap-2">
              <button
                className="button-secondary px-3 py-2 text-sm"
                onClick={resetForm}
                disabled={busy}
              >
                {t("form.clear")}
              </button>
              <button
                className="button-primary px-4 py-2 text-sm disabled:opacity-50"
                onClick={() => void save()}
                disabled={busy || !form.serverId.trim() || !form.url.trim()}
              >
                {busy ? t("form.saving") : t("form.save")}
              </button>
            </div>
          </div>
        </section>}
      </div>

      {diagnosticId && (
        <section className="glass-panel min-w-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-medium">
                {t("diagnostics.title")} ·{" "}
                <span className="font-mono">{diagnosticId}</span>
              </h2>
              <p className="text-xs text-muted-foreground">
                {t("diagnostics.description")}
              </p>
            </div>
            <button
              className="button-secondary px-2 py-1 text-xs"
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
                  <Count
                    title={t("diagnostics.tools")}
                    value={discovery.tools.length}
                  />
                  <Count
                    title={t("diagnostics.resources")}
                    value={discovery.resources.length}
                  />
                  <Count
                    title={t("diagnostics.prompts")}
                    value={discovery.prompts.length}
                  />
                  <Count
                    title={t("diagnostics.apps")}
                    value={
                      discovery.mcp_apps.supported
                        ? discovery.mcp_apps.resourceUris.length
                        : 0
                    }
                  />
                </div>
              )}
              {discovery.mcp_apps.resourceUris.length > 0 && (
                <div className="rounded-md bg-muted/30 p-3 text-xs">
                  <div className="font-medium">{t("diagnostics.appUris")}</div>
                  {discovery.mcp_apps.resourceUris.map((uri) => (
                    <div
                      key={uri}
                      className="mt-1 break-all font-mono text-muted-foreground"
                    >
                      {uri}
                    </div>
                  ))}
                </div>
              )}
              {discovery.warnings.length > 0 && (
                <div className="notice notice--warning block">
                  {discovery.warnings.map((warning, index) => (
                    <p key={`${warning.capability}-${index}`}>
                      <strong>{warning.capability}</strong> · {warning.category}
                      : {warning.message}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}
      </div>
    </main>
  );
}

function DiagnosticStatus({
  result,
  t,
}: {
  result: McpHealth;
  t: PageTranslator;
}) {
  return (
    <div
      role={result.ok ? "status" : "alert"}
      className={`notice mt-3 block ${result.ok ? "notice--success" : "notice--danger"}`}
    >
      <strong className={`badge ${result.ok ? "badge--success" : "badge--danger"}`}>
        {result.ok
          ? t("diagnostics.connected")
          : t("diagnostics.failed", {
              category: result.category || t("diagnostics.unknown"),
            })}
      </strong>
      {result.message && (
        <p className="mt-1 break-words text-xs text-muted-foreground">
          {result.message}
        </p>
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

function Badge({ children, tone }: { children: React.ReactNode; tone?: "brand" | "success" | "warning" }) {
  return (
    <span className={`badge${tone ? ` badge--${tone}` : ""}`}>
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
      className={`${danger ? "button-danger" : "button-secondary"} px-2 py-1 text-xs disabled:opacity-50`}
    >
      {children}
    </button>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="text-xs text-muted-foreground">
      <span className="mb-1 block">{label}</span>
      {children}
    </label>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <main className="page-container flex min-h-screen items-center justify-center p-8">
      {children}
    </main>
  );
}
