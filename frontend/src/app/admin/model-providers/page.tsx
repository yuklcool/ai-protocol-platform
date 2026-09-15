"use client";

import NextLink from "next/link";
import { useEffect, useState } from "react";

import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import { fetchWithAuth } from "@/lib/apiClient";

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

const emptyProvider = { providerId: "", name: "", baseUrl: "", apiKeyRef: "", enabled: true };
const emptyModel = {
  modelId: "",
  apiName: "",
  providerId: "",
  tier: "default" as const,
  contextWindow: "128000",
  maxOutputTokens: "8192",
  description: "",
  supportsTools: true,
  supportsReasoning: false,
  supportsResponsesApi: false,
  supportsVision: false,
  residency: "global" as const,
  enabled: true,
};

async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : body?.detail ? JSON.stringify(body.detail) : fallback;
}

export default function ModelProvidersPage() {
  const { user, loading } = useAuth();
  const { state, isAdmin, isPlatform } = useAdminScope(!loading && !!user);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [providerForm, setProviderForm] = useState(emptyProvider);
  const [modelForm, setModelForm] = useState(emptyModel);
  const [notice, setNotice] = useState<string | null>(null);
  const [probe, setProbe] = useState<{ label: string; result: Probe } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const [p, m] = await Promise.all([fetchWithAuth(API), fetchWithAuth(`${API}/models`)]);
    if (!p.ok || !m.ok) {
      setNotice(!p.ok ? await detail(p, "Could not load providers.") : await detail(m, "Could not load models."));
      return;
    }
    setProviders(await p.json());
    setModels(await m.json());
  };

  useEffect(() => {
    if (!loading && user && isPlatform) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, user, isPlatform]);

  const saveProvider = async () => {
    const id = providerForm.providerId.trim();
    if (!id || !providerForm.baseUrl.trim()) return;
    setBusy(true); setNotice(null);
    try {
      const response = await fetchWithAuth(`${API}/${encodeURIComponent(id)}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: providerForm.name.trim() || id,
          kind: "openai-compatible",
          base_url: providerForm.baseUrl.trim(),
          api_key_ref: providerForm.apiKeyRef.trim() || null,
          enabled: providerForm.enabled,
        }),
      });
      if (!response.ok) return setNotice(await detail(response, `Could not save ${id}.`));
      setProviderForm(emptyProvider); setNotice(`Saved provider ${id}.`); await load();
    } finally { setBusy(false); }
  };

  const saveModel = async () => {
    const id = modelForm.modelId.trim();
    if (!id || !modelForm.apiName.trim() || !modelForm.providerId) return;
    setBusy(true); setNotice(null);
    try {
      const response = await fetchWithAuth(`${API}/models/${encodeURIComponent(id)}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_name: modelForm.apiName.trim(), provider_id: modelForm.providerId, tier: modelForm.tier,
          context_window: Number(modelForm.contextWindow), max_output_tokens: Number(modelForm.maxOutputTokens),
          description: modelForm.description.trim(), supports_tools: modelForm.supportsTools,
          supports_reasoning: modelForm.supportsReasoning, supports_responses_api: modelForm.supportsResponsesApi,
          supports_vision: modelForm.supportsVision, residency: modelForm.residency, enabled: modelForm.enabled,
        }),
      });
      if (!response.ok) return setNotice(await detail(response, `Could not save ${id}.`));
      setModelForm(emptyModel); setNotice(`Saved model ${id}. It is now available through the effective registry.`); await load();
    } finally { setBusy(false); }
  };

  const removeProvider = async (item: Provider) => {
    if (!window.confirm(`Delete provider ${item.provider_id}?`)) return;
    const response = await fetchWithAuth(`${API}/${encodeURIComponent(item.provider_id)}`, { method: "DELETE" });
    if (!response.ok) return setNotice(await detail(response, "Could not delete provider."));
    setNotice(`Deleted ${item.provider_id}.`); await load();
  };

  const removeModel = async (item: Model) => {
    if (!window.confirm(`Delete model ${item.model_id}?`)) return;
    const response = await fetchWithAuth(`${API}/models/${encodeURIComponent(item.model_id)}`, { method: "DELETE" });
    if (!response.ok) return setNotice(await detail(response, "Could not delete model."));
    setNotice(`Deleted ${item.model_id}.`); await load();
  };

  const testProvider = async (item: Provider) => {
    setProbe(null);
    const response = await fetchWithAuth(`${API}/${encodeURIComponent(item.provider_id)}/test`, { method: "POST" });
    if (!response.ok) return setNotice(await detail(response, "Provider test failed."));
    setProbe({ label: `Provider ${item.provider_id}`, result: await response.json() });
  };

  const testModel = async (item: Model, mode: "completion" | "tool_call") => {
    setProbe(null);
    const response = await fetchWithAuth(`${API}/models/${encodeURIComponent(item.model_id)}/test`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }),
    });
    if (!response.ok) return setNotice(await detail(response, "Model test failed."));
    setProbe({ label: `${item.model_id} · ${mode}`, result: await response.json() });
  };

  if (loading || state === "loading") return <Centered>Loading…</Centered>;
  if (!user) return <SignInRequired />;
  if (state === "error") return <Centered>Couldn&apos;t reach the admin service.</Centered>;
  if (!isAdmin) return <Centered>Administrative scope required.</Centered>;
  if (!isPlatform) return <Centered>Platform admin required for model provider configuration.</Centered>;

  return (
    <main className="mx-auto max-w-7xl p-6">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Model Providers</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            Configure OpenAI-compatible endpoints and dynamic models. API keys are secret references only; plaintext keys are rejected by the backend.
          </p>
        </div>
        <NextLink href="/admin" className="rounded-md border px-3 py-1.5 text-sm hover:bg-muted/40">Back to Admin</NextLink>
      </header>

      {notice && <div className="mb-4 rounded-md border px-3 py-2 text-sm">{notice}</div>}
      {probe && <div className="mb-4 rounded-md border p-3 text-sm"><b>{probe.label}</b><pre className="mt-2 overflow-auto text-xs">{JSON.stringify(probe.result, null, 2)}</pre></div>}

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-lg border p-4">
          <h2 className="font-medium">Providers</h2>
          <div className="mt-3 space-y-3">
            {providers.map((item) => <div key={item.provider_id} className="rounded-md border p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2"><div><b>{item.provider_id}</b> <Badge>{item.enabled ? "enabled" : "disabled"}</Badge></div><div className="flex gap-2"><Button onClick={() => void testProvider(item)}>Test</Button><Button onClick={() => { setProviderForm({ providerId: item.provider_id, name: item.name, baseUrl: item.base_url, apiKeyRef: item.api_key_ref ?? "", enabled: item.enabled }); }}>Edit</Button><Button onClick={() => void removeProvider(item)}>Delete</Button></div></div>
              <p className="mt-1 break-all text-xs text-muted-foreground">{item.base_url}</p>
              <p className="mt-1 text-xs text-muted-foreground">Secret: {item.has_api_key ? item.api_key_ref ?? "configured" : "none"}</p>
            </div>)}
          </div>
          <div className="mt-5 border-t pt-4"><h3 className="text-sm font-medium">Add / edit provider</h3><div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Input placeholder="provider id" value={providerForm.providerId} onChange={(v) => setProviderForm({ ...providerForm, providerId: v })}/>
            <Input placeholder="display name" value={providerForm.name} onChange={(v) => setProviderForm({ ...providerForm, name: v })}/>
            <div className="sm:col-span-2"><Input placeholder="https://api.example.com/v1" value={providerForm.baseUrl} onChange={(v) => setProviderForm({ ...providerForm, baseUrl: v })}/></div>
            <div className="sm:col-span-2"><Input placeholder="${PROVIDER_API_KEY}" value={providerForm.apiKeyRef} onChange={(v) => setProviderForm({ ...providerForm, apiKeyRef: v })}/></div>
            <label className="text-sm"><input type="checkbox" checked={providerForm.enabled} onChange={(e) => setProviderForm({ ...providerForm, enabled: e.target.checked })}/> <span className="ml-1">Enabled</span></label>
          </div><Button onClick={() => void saveProvider()} disabled={busy}>Save provider</Button></div>
        </section>

        <section className="rounded-lg border p-4">
          <h2 className="font-medium">Dynamic models</h2>
          <div className="mt-3 space-y-3">
            {models.map((item) => <div key={item.model_id} className="rounded-md border p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2"><div><b>{item.model_id}</b> <Badge>{item.provider_id}</Badge> <Badge>{item.tier}</Badge></div><div className="flex flex-wrap gap-2"><Button onClick={() => void testModel(item, "completion")}>Completion</Button><Button onClick={() => void testModel(item, "tool_call")} disabled={!item.supports_tools}>Tool call</Button><Button onClick={() => { setModelForm({ modelId: item.model_id, apiName: item.api_name, providerId: item.provider_id, tier: item.tier, contextWindow: String(item.context_window), maxOutputTokens: String(item.max_output_tokens), description: item.description, supportsTools: item.supports_tools, supportsReasoning: item.supports_reasoning, supportsResponsesApi: item.supports_responses_api, supportsVision: item.supports_vision, residency: item.residency, enabled: item.enabled }); }}>Edit</Button><Button onClick={() => void removeModel(item)}>Delete</Button></div></div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">{item.api_name}</p>
              <p className="mt-1 text-xs text-muted-foreground">context {item.context_window.toLocaleString()} · output {item.max_output_tokens.toLocaleString()} · {item.residency}</p>
            </div>)}
          </div>
          <div className="mt-5 border-t pt-4"><h3 className="text-sm font-medium">Add / edit model</h3><div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Input placeholder="model id" value={modelForm.modelId} onChange={(v) => setModelForm({ ...modelForm, modelId: v })}/>
            <Input placeholder="provider id" value={modelForm.providerId} onChange={(v) => setModelForm({ ...modelForm, providerId: v })}/>
            <Input placeholder="API model name" value={modelForm.apiName} onChange={(v) => setModelForm({ ...modelForm, apiName: v })}/>
            <select className="rounded-md border bg-background px-2 py-2 text-sm" value={modelForm.tier} onChange={(e) => setModelForm({ ...modelForm, tier: e.target.value as Model["tier"] })}><option value="default">default</option><option value="smart">smart</option><option value="fast">fast</option></select>
            <Input placeholder="context window" value={modelForm.contextWindow} onChange={(v) => setModelForm({ ...modelForm, contextWindow: v })}/>
            <Input placeholder="max output tokens" value={modelForm.maxOutputTokens} onChange={(v) => setModelForm({ ...modelForm, maxOutputTokens: v })}/>
            <div className="sm:col-span-2"><Input placeholder="description" value={modelForm.description} onChange={(v) => setModelForm({ ...modelForm, description: v })}/></div>
            <select className="rounded-md border bg-background px-2 py-2 text-sm" value={modelForm.residency} onChange={(e) => setModelForm({ ...modelForm, residency: e.target.value as Model["residency"] })}><option value="global">global</option><option value="eu">eu</option><option value="us">us</option></select>
            <div className="flex flex-wrap gap-3 text-xs">{([['supportsTools','tools'],['supportsReasoning','reasoning'],['supportsResponsesApi','responses'],['supportsVision','vision'],['enabled','enabled']] as const).map(([key,label]) => <label key={key}><input type="checkbox" checked={modelForm[key]} onChange={(e) => setModelForm({ ...modelForm, [key]: e.target.checked })}/> {label}</label>)}</div>
          </div><Button onClick={() => void saveModel()} disabled={busy}>Save model</Button></div>
        </section>
      </div>
    </main>
  );
}

function Input({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) { return <input className="w-full rounded-md border bg-background px-2 py-2 text-sm" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />; }
function Button({ children, onClick, disabled = false }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) { return <button type="button" disabled={disabled} onClick={onClick} className="mt-2 rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted/40 disabled:opacity-50">{children}</button>; }
function Badge({ children }: { children: React.ReactNode }) { return <span className="ml-1 rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground">{children}</span>; }
function Centered({ children }: { children: React.ReactNode }) { return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>; }
