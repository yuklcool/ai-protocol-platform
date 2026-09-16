"use client";

import NextLink from "next/link";
import { useEffect, useState } from "react";

import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useI18n } from "@/contexts/I18nContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { fetchWithAuth } from "@/lib/apiClient";
import {
  translateModelProvider,
  type ModelProviderTranslationKey,
} from "@/lib/i18n/modelProvider";

type Provider = {
  provider_id: string;
  name: string;
  kind: string;
  base_url: string;
  api_key_ref: string | null;
  has_api_key: boolean;
  enabled: boolean;
};

type Model = {
  model_id: string;
  api_name: string;
  provider_id: string;
  tier: "default" | "smart" | "fast";
  context_window: number;
  max_output_tokens: number;
  description: string;
  supports_tools: boolean;
  supports_reasoning: boolean;
  supports_responses_api: boolean;
  supports_vision: boolean;
  residency: "eu" | "us" | "global";
  enabled: boolean;
};

type RegistryModel = {
  model_id: string;
  api_name: string;
  provider: string;
  provider_id: string | null;
  tier: "default" | "smart" | "fast";
  residency: "eu" | "us" | "global";
  source: string;
};

type RegistrySettings = {
  platform_default: string;
  tier_defaults: { default: string; smart: string; fast: string };
  available_models: RegistryModel[];
  source: "yaml" | "database";
  writable: boolean;
};

type Probe = {
  ok: boolean;
  category?: string | null;
  message?: string | null;
  content?: string | null;
  tool_called?: boolean | null;
  latency_ms?: number | null;
  model_count?: number | null;
};

const API = "/api/proxy/api/admin/model-providers";
const SETTINGS_API = "/api/proxy/api/admin/model-registry/settings";

const emptyProvider = {
  providerId: "",
  name: "",
  baseUrl: "",
  apiKeyRef: "",
  enabled: true,
};

const emptyModel = {
  modelId: "",
  apiName: "",
  providerId: "",
  tier: "default" as Model["tier"],
  contextWindow: "128000",
  maxOutputTokens: "8192",
  description: "",
  supportsTools: true,
  supportsReasoning: false,
  supportsResponsesApi: false,
  supportsVision: false,
  residency: "global" as Model["residency"],
  enabled: true,
};

const emptySettingsForm = {
  platformDefault: "",
  default: "",
  smart: "",
  fast: "",
};

async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => null);
  return typeof body?.detail === "string"
    ? body.detail
    : body?.detail
      ? JSON.stringify(body.detail)
      : fallback;
}

export default function ModelProvidersPage() {
  const { user, loading } = useAuth();
  const { locale } = useI18n();
  const { state, isAdmin, isPlatform } = useAdminScope(!loading && !!user);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [registrySettings, setRegistrySettings] = useState<RegistrySettings | null>(null);
  const [providerForm, setProviderForm] = useState(emptyProvider);
  const [modelForm, setModelForm] = useState(emptyModel);
  const [settingsForm, setSettingsForm] = useState(emptySettingsForm);
  const [notice, setNotice] = useState<string | null>(null);
  const [probe, setProbe] = useState<{ label: string; result: Probe } | null>(null);
  const [busy, setBusy] = useState(false);

  const t = (
    key: ModelProviderTranslationKey,
    params: Record<string, string | number> = {},
  ) => translateModelProvider(locale, key, params);

  const load = async () => {
    const [p, m, s] = await Promise.all([
      fetchWithAuth(API),
      fetchWithAuth(`${API}/models`),
      fetchWithAuth(SETTINGS_API),
    ]);
    if (!p.ok || !m.ok || !s.ok) {
      if (!p.ok) setNotice(await detail(p, t("load.providers")));
      else if (!m.ok) setNotice(await detail(m, t("load.models")));
      else setNotice(await detail(s, t("load.defaults")));
      return;
    }
    const [providerRows, modelRows, settings] = await Promise.all([
      p.json(),
      m.json(),
      s.json(),
    ]);
    setProviders(providerRows);
    setModels(modelRows);
    setRegistrySettings(settings);
    setSettingsForm({
      platformDefault: settings.platform_default,
      default: settings.tier_defaults.default,
      smart: settings.tier_defaults.smart,
      fast: settings.tier_defaults.fast,
    });
  };

  useEffect(() => {
    if (!loading && user && isPlatform) {
      void load().catch(() => setNotice(t("load.configuration")));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user, isPlatform, locale]);

  const saveProvider = async () => {
    const id = providerForm.providerId.trim();
    if (!id || !providerForm.baseUrl.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetchWithAuth(`${API}/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: providerForm.name.trim() || id,
          kind: "openai-compatible",
          base_url: providerForm.baseUrl.trim(),
          api_key_ref: providerForm.apiKeyRef.trim() || null,
          enabled: providerForm.enabled,
        }),
      });
      if (!response.ok) {
        return setNotice(await detail(response, t("save.providerFailed", { id })));
      }
      setProviderForm(emptyProvider);
      setNotice(t("save.providerOk", { id }));
      await load();
    } catch {
      setNotice(t("save.configurationFailed"));
    } finally {
      setBusy(false);
    }
  };

  const saveModel = async () => {
    const id = modelForm.modelId.trim();
    if (!id || !modelForm.apiName.trim() || !modelForm.providerId) return;
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetchWithAuth(`${API}/models/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_name: modelForm.apiName.trim(),
          provider_id: modelForm.providerId,
          tier: modelForm.tier,
          context_window: Number(modelForm.contextWindow),
          max_output_tokens: Number(modelForm.maxOutputTokens),
          description: modelForm.description.trim(),
          supports_tools: modelForm.supportsTools,
          supports_reasoning: modelForm.supportsReasoning,
          supports_responses_api: modelForm.supportsResponsesApi,
          supports_vision: modelForm.supportsVision,
          residency: modelForm.residency,
          enabled: modelForm.enabled,
        }),
      });
      if (!response.ok) {
        return setNotice(await detail(response, t("save.modelFailed", { id })));
      }
      setModelForm(emptyModel);
      setNotice(t("save.modelOk", { id }));
      await load();
    } catch {
      setNotice(t("save.configurationFailed"));
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = async () => {
    const values = [
      settingsForm.platformDefault,
      settingsForm.default,
      settingsForm.smart,
      settingsForm.fast,
    ];
    if (values.some((value) => !value.trim())) {
      setNotice(t("save.chooseRouting"));
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const response = await fetchWithAuth(SETTINGS_API, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform_default: settingsForm.platformDefault,
          tier_defaults: {
            default: settingsForm.default,
            smart: settingsForm.smart,
            fast: settingsForm.fast,
          },
        }),
      });
      if (!response.ok) {
        return setNotice(await detail(response, t("save.defaultsFailed")));
      }
      setNotice(t("save.defaultsOk"));
      await load();
    } catch {
      setNotice(t("save.defaultsRetry"));
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (action: () => Promise<void>) => {
    setBusy(true);
    setNotice(null);
    try {
      await action();
    } catch {
      setNotice(t("request.failed"));
    } finally {
      setBusy(false);
    }
  };

  const removeProvider = async (item: Provider) => {
    if (!window.confirm(t("delete.providerConfirm", { id: item.provider_id }))) return;
    const response = await fetchWithAuth(
      `${API}/${encodeURIComponent(item.provider_id)}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      return setNotice(await detail(response, t("delete.providerFailed")));
    }
    setNotice(t("delete.ok", { id: item.provider_id }));
    await load();
  };

  const removeModel = async (item: Model) => {
    if (!window.confirm(t("delete.modelConfirm", { id: item.model_id }))) return;
    const response = await fetchWithAuth(
      `${API}/models/${encodeURIComponent(item.model_id)}`,
      { method: "DELETE" },
    );
    if (!response.ok) {
      return setNotice(await detail(response, t("delete.modelFailed")));
    }
    setNotice(t("delete.ok", { id: item.model_id }));
    await load();
  };

  const testProvider = async (item: Provider) => {
    setProbe(null);
    const response = await fetchWithAuth(
      `${API}/${encodeURIComponent(item.provider_id)}/test`,
      { method: "POST" },
    );
    if (!response.ok) {
      return setNotice(await detail(response, t("probe.providerFailed")));
    }
    setProbe({
      label: t("probe.providerLabel", { id: item.provider_id }),
      result: await response.json(),
    });
  };

  const testModel = async (item: Model, mode: "completion" | "tool_call") => {
    setProbe(null);
    const response = await fetchWithAuth(
      `${API}/models/${encodeURIComponent(item.model_id)}/test`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      },
    );
    if (!response.ok) {
      return setNotice(await detail(response, t("probe.modelFailed")));
    }
    setProbe({
      label: `${item.model_id} · ${mode}`,
      result: await response.json(),
    });
  };

  if (loading || state === "loading") return <Centered>{t("state.loading")}</Centered>;
  if (!user) return <SignInRequired />;
  if (state === "error") return <Centered>{t("state.adminUnavailable")}</Centered>;
  if (!isAdmin) return <Centered>{t("state.adminRequired")}</Centered>;
  if (!isPlatform) return <Centered>{t("state.platformRequired")}</Centered>;

  const registryModels = registrySettings?.available_models ?? [];

  return (
    <main className="mx-auto max-w-7xl p-6">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{t("title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            {t("description", { secret: "${PROVIDER_API_KEY}" })}
          </p>
        </div>
        <NextLink
          href="/admin"
          className="rounded-md border px-3 py-1.5 text-sm hover:bg-muted/40"
        >
          {t("back")}
        </NextLink>
      </header>

      {notice && (
        <div className="mb-4 rounded-md border px-3 py-2 text-sm">{notice}</div>
      )}
      {probe && (
        <div className="mb-4 rounded-md border p-3 text-sm">
          <b>{probe.label}</b>
          <pre className="mt-2 overflow-auto text-xs">
            {JSON.stringify(probe.result, null, 2)}
          </pre>
        </div>
      )}

      <section className="mb-6 rounded-lg border p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-medium">{t("routing.title")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("routing.description")}
            </p>
          </div>
          {registrySettings && (
            <div className="text-xs text-muted-foreground">
              {t("routing.source")} <Badge>{registrySettings.source}</Badge>{" "}
              {registrySettings.writable
                ? t("routing.database")
                : t("routing.gitops")}
            </div>
          )}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <ModelSelect
            label={t("routing.platformDefault")}
            emptyLabel={t("routing.notConfigured")}
            value={settingsForm.platformDefault}
            models={registryModels}
            onChange={(value) =>
              setSettingsForm({ ...settingsForm, platformDefault: value })
            }
          />
          <ModelSelect
            label={t("routing.defaultTier")}
            emptyLabel={t("routing.notConfigured")}
            value={settingsForm.default}
            models={registryModels}
            onChange={(value) => setSettingsForm({ ...settingsForm, default: value })}
          />
          <ModelSelect
            label={t("routing.smartTier")}
            emptyLabel={t("routing.notConfigured")}
            value={settingsForm.smart}
            models={registryModels}
            onChange={(value) => setSettingsForm({ ...settingsForm, smart: value })}
          />
          <ModelSelect
            label={t("routing.fastTier")}
            emptyLabel={t("routing.notConfigured")}
            value={settingsForm.fast}
            models={registryModels}
            onChange={(value) => setSettingsForm({ ...settingsForm, fast: value })}
          />
        </div>
        <Button
          onClick={() => void saveSettings()}
          disabled={busy || !registrySettings?.writable}
        >
          {t("routing.save")}
        </Button>
        {!registrySettings?.writable && registrySettings && (
          <p className="mt-2 text-xs text-muted-foreground">{t("routing.readonly")}</p>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-lg border p-4">
          <h2 className="font-medium">{t("providers.title")}</h2>
          <div className="mt-3 space-y-3">
            {providers.map((item) => (
              <div key={item.provider_id} className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <b>{item.provider_id}</b>{" "}
                    <Badge>
                      {item.enabled ? t("providers.enabled") : t("providers.disabled")}
                    </Badge>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      disabled={busy}
                      onClick={() => void runAction(() => testProvider(item))}
                    >
                      {t("providers.test")}
                    </Button>
                    <Button
                      onClick={() => {
                        setProviderForm({
                          providerId: item.provider_id,
                          name: item.name,
                          baseUrl: item.base_url,
                          apiKeyRef: item.api_key_ref ?? "",
                          enabled: item.enabled,
                        });
                      }}
                    >
                      {t("providers.edit")}
                    </Button>
                    <Button
                      disabled={busy}
                      onClick={() => void runAction(() => removeProvider(item))}
                    >
                      {t("providers.delete")}
                    </Button>
                  </div>
                </div>
                <p className="mt-1 break-all text-xs text-muted-foreground">
                  {item.base_url}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("providers.secret", {
                    value: item.has_api_key
                      ? item.api_key_ref ?? t("providers.secretConfigured")
                      : t("providers.secretNone"),
                  })}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-5 border-t pt-4">
            <h3 className="text-sm font-medium">{t("providers.formTitle")}</h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <Input
                placeholder={t("providers.id")}
                value={providerForm.providerId}
                onChange={(value) =>
                  setProviderForm({ ...providerForm, providerId: value })
                }
              />
              <Input
                placeholder={t("providers.name")}
                value={providerForm.name}
                onChange={(value) => setProviderForm({ ...providerForm, name: value })}
              />
              <div className="sm:col-span-2">
                <Input
                  placeholder="https://api.example.com/v1"
                  value={providerForm.baseUrl}
                  onChange={(value) =>
                    setProviderForm({ ...providerForm, baseUrl: value })
                  }
                />
              </div>
              <div className="sm:col-span-2">
                <Input
                  placeholder="${PROVIDER_API_KEY}"
                  value={providerForm.apiKeyRef}
                  onChange={(value) =>
                    setProviderForm({ ...providerForm, apiKeyRef: value })
                  }
                />
              </div>
              <label className="text-sm">
                <input
                  type="checkbox"
                  checked={providerForm.enabled}
                  onChange={(event) =>
                    setProviderForm({
                      ...providerForm,
                      enabled: event.target.checked,
                    })
                  }
                />{" "}
                <span className="ml-1">{t("providers.enabledLabel")}</span>
              </label>
            </div>
            <Button onClick={() => void saveProvider()} disabled={busy}>
              {t("providers.save")}
            </Button>
          </div>
        </section>

        <section className="rounded-lg border p-4">
          <h2 className="font-medium">{t("models.title")}</h2>
          <div className="mt-3 space-y-3">
            {models.map((item) => (
              <div key={item.model_id} className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <b>{item.model_id}</b> <Badge>{item.provider_id}</Badge>{" "}
                    <Badge>{item.tier}</Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      disabled={busy}
                      onClick={() => void runAction(() => testModel(item, "completion"))}
                    >
                      {t("models.completion")}
                    </Button>
                    <Button
                      disabled={busy || !item.supports_tools}
                      onClick={() => void runAction(() => testModel(item, "tool_call"))}
                    >
                      {t("models.toolCall")}
                    </Button>
                    <Button
                      onClick={() => {
                        setModelForm({
                          modelId: item.model_id,
                          apiName: item.api_name,
                          providerId: item.provider_id,
                          tier: item.tier,
                          contextWindow: String(item.context_window),
                          maxOutputTokens: String(item.max_output_tokens),
                          description: item.description,
                          supportsTools: item.supports_tools,
                          supportsReasoning: item.supports_reasoning,
                          supportsResponsesApi: item.supports_responses_api,
                          supportsVision: item.supports_vision,
                          residency: item.residency,
                          enabled: item.enabled,
                        });
                      }}
                    >
                      {t("models.edit")}
                    </Button>
                    <Button
                      disabled={busy}
                      onClick={() => void runAction(() => removeModel(item))}
                    >
                      {t("models.delete")}
                    </Button>
                  </div>
                </div>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {item.api_name}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("models.stats", {
                    context: item.context_window.toLocaleString(),
                    output: item.max_output_tokens.toLocaleString(),
                    residency: item.residency,
                  })}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-5 border-t pt-4">
            <h3 className="text-sm font-medium">{t("models.formTitle")}</h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <Input
                placeholder={t("models.id")}
                value={modelForm.modelId}
                onChange={(value) => setModelForm({ ...modelForm, modelId: value })}
              />
              <Input
                placeholder={t("models.providerId")}
                value={modelForm.providerId}
                onChange={(value) => setModelForm({ ...modelForm, providerId: value })}
              />
              <Input
                placeholder={t("models.apiName")}
                value={modelForm.apiName}
                onChange={(value) => setModelForm({ ...modelForm, apiName: value })}
              />
              <select
                className="rounded-md border bg-background px-2 py-2 text-sm"
                aria-label={t("models.tier")}
                value={modelForm.tier}
                onChange={(event) =>
                  setModelForm({
                    ...modelForm,
                    tier: event.target.value as Model["tier"],
                  })
                }
              >
                <option value="default">default</option>
                <option value="smart">smart</option>
                <option value="fast">fast</option>
              </select>
              <Input
                placeholder={t("models.contextWindow")}
                value={modelForm.contextWindow}
                onChange={(value) =>
                  setModelForm({ ...modelForm, contextWindow: value })
                }
              />
              <Input
                placeholder={t("models.maxOutput")}
                value={modelForm.maxOutputTokens}
                onChange={(value) =>
                  setModelForm({ ...modelForm, maxOutputTokens: value })
                }
              />
              <div className="sm:col-span-2">
                <Input
                  placeholder={t("models.description")}
                  value={modelForm.description}
                  onChange={(value) =>
                    setModelForm({ ...modelForm, description: value })
                  }
                />
              </div>
              <select
                className="rounded-md border bg-background px-2 py-2 text-sm"
                aria-label={t("models.residency")}
                value={modelForm.residency}
                onChange={(event) =>
                  setModelForm({
                    ...modelForm,
                    residency: event.target.value as Model["residency"],
                  })
                }
              >
                <option value="global">global</option>
                <option value="eu">eu</option>
                <option value="us">us</option>
              </select>
              <div className="flex flex-wrap gap-3 text-xs">
                {(
                  [
                    ["supportsTools", "models.cap.tools"],
                    ["supportsReasoning", "models.cap.reasoning"],
                    ["supportsResponsesApi", "models.cap.responses"],
                    ["supportsVision", "models.cap.vision"],
                    ["enabled", "models.cap.enabled"],
                  ] as const
                ).map(([key, labelKey]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={modelForm[key]}
                      onChange={(event) =>
                        setModelForm({ ...modelForm, [key]: event.target.checked })
                      }
                    />{" "}
                    {t(labelKey)}
                  </label>
                ))}
              </div>
            </div>
            <Button onClick={() => void saveModel()} disabled={busy}>
              {t("models.save")}
            </Button>
          </div>
        </section>
      </div>
    </main>
  );
}

function ModelSelect({
  label,
  emptyLabel,
  value,
  models,
  onChange,
}: {
  label: string;
  emptyLabel: string;
  value: string;
  models: RegistryModel[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      <select
        className="w-full rounded-md border bg-background px-2 py-2 text-sm"
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{emptyLabel}</option>
        {models.map((model) => (
          <option key={model.model_id} value={model.model_id}>
            {model.model_id} · {model.tier} · {model.residency} · {model.source}
          </option>
        ))}
      </select>
    </label>
  );
}

function Input({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <input
      className="w-full rounded-md border bg-background px-2 py-2 text-sm"
      value={value}
      placeholder={placeholder}
      aria-label={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function Button({
  children,
  onClick,
  disabled = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="mt-2 rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted/40 disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="ml-1 rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground">
      {children}
    </span>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>;
}
