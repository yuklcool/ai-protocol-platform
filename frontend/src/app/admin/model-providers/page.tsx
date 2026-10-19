"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { SignInRequired } from "@/components/chat/SignInRequired";
import { useAuth } from "@/contexts/AuthContext";
import { useAdminScope } from "@/hooks/useAdminScope";
import {
  MODEL_API as API,
  categoryHelp,
  internalId,
  jsonWrite,
  modelRequest,
  type Check,
  type Current,
  type Discovery,
  type Model,
  type Provider,
  type Registry,
} from "@/lib/modelSetup";

const fieldClass =
  "glass-control mt-1 w-full min-w-0 px-3 py-2 text-sm";
const buttonClass =
  "rounded-md border px-3 py-2 text-sm hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-50";
const serviceDefault = {
  name: "",
  base_url: "",
  env: "OPENAI_API_KEY",
  noKey: false,
  enabled: true,
};
const modelDefault = {
  api_name: "",
  context_window: 128000,
  max_output_tokens: 8192,
  description: "",
  tier: "default" as Model["tier"],
  residency: "global" as Model["residency"],
  supports_tools: true,
  supports_reasoning: false,
  supports_responses_api: false,
  supports_vision: false,
  enabled: true,
  inputPrice: "",
  outputPrice: "",
};
type View = "service" | "model" | "test" | null;

export default function ModelProvidersPage() {
  const { user, loading } = useAuth();
  const { state, isAdmin, isPlatform } = useAdminScope(!loading && !!user);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [current, setCurrent] = useState<Current | null>(null);
  const [dataLoading, setDataLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  const [view, setView] = useState<View>(null);
  const [providerId, setProviderId] = useState("");
  const [modelId, setModelId] = useState("");
  const [editing, setEditing] = useState(false);
  const [service, setService] = useState(serviceDefault);
  const [form, setForm] = useState(modelDefault);
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoverQuery, setDiscoverQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const [checks, setChecks] = useState<{
    completion: Check | null;
    tool_call: Check | null;
  }>({ completion: null, tool_call: null });
  const [testing, setTesting] = useState<string | null>(null);
  const [routing, setRouting] = useState<Registry | null>(null);
  const testController = useRef<AbortController | null>(null);
  const discoveryController = useRef<AbortController | null>(null);
  const editorHeading = useRef<HTMLHeadingElement>(null);
  const activeModel = models.find((model) => model.model_id === modelId);
  const activeProvider = providers.find(
    (provider) => provider.provider_id === providerId,
  );

  async function load(signal?: AbortSignal) {
    const [p, m, r, c] = await Promise.all([
      modelRequest<Provider[]>(API, { signal }),
      modelRequest<Model[]>(`${API}/models`, { signal }),
      modelRequest<Registry>("/model-registry/settings", { signal }),
      modelRequest<Current>(`${API}/models/current`, { signal }),
    ]);
    if (signal?.aborted) return;
    setProviders(p);
    setModels(m);
    setRegistry(r);
    setRouting(r);
    setCurrent(c);
    setLoadError("");
  }
  useEffect(() => {
    if (loading || !user || !isPlatform) return;
    const controller = new AbortController();
    setDataLoading(true);
    void load(controller.signal)
      .catch((error) => {
        if (!controller.signal.aborted) setLoadError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setDataLoading(false);
      });
    return () => controller.abort();
  }, [loading, user, isPlatform, reload]);
  useEffect(() => {
    editorHeading.current?.focus();
  }, [view, modelId]);
  useEffect(
    () => () => {
      testController.current?.abort();
      discoveryController.current?.abort();
    },
    [],
  );

  function close() {
    testController.current?.abort();
    discoveryController.current?.abort();
    setView(null);
    setDiscovering(false);
    setFailure("");
    setNotice("");
  }
  function newService(provider?: Provider) {
    close();
    setEditing(!!provider);
    setProviderId(provider?.provider_id || internalId("service"));
    setService(
      provider
        ? {
            name: provider.name,
            base_url: provider.base_url,
            env:
              provider.api_key_ref?.replace(/^\$\{(.+)\}$/, "$1") ||
              "OPENAI_API_KEY",
            noKey: !provider.api_key_ref,
            enabled: provider.enabled,
          }
        : serviceDefault,
    );
    setView("service");
  }
  async function discover(id: string) {
    discoveryController.current?.abort();
    const controller = new AbortController();
    discoveryController.current = controller;
    setDiscovering(true);
    setDiscovery(null);
    setDiscoverQuery("");
    try {
      const result = await modelRequest<Discovery>(
        `${API}/${encodeURIComponent(id)}/test`,
        { method: "POST", signal: controller.signal },
      );
      if (!controller.signal.aborted) setDiscovery(result);
    } catch (error) {
      if (!controller.signal.aborted)
        setDiscovery({
          ok: false,
          category: "network",
          message: (error as Error).message,
          models: [],
          model_count: null,
        });
    } finally {
      if (!controller.signal.aborted) setDiscovering(false);
    }
  }
  function editModel(provider: string, model?: Model) {
    close();
    setProviderId(provider);
    setModelId(model?.model_id || internalId("model"));
    setEditing(!!model);
    setDiscovery(null);
    setForm(
      model
        ? {
            api_name: model.api_name,
            context_window: model.context_window,
            max_output_tokens: model.max_output_tokens,
            description: model.description,
            tier: model.tier,
            residency: model.residency,
            supports_tools: model.supports_tools,
            supports_reasoning: model.supports_reasoning,
            supports_responses_api: model.supports_responses_api,
            supports_vision: model.supports_vision,
            enabled: model.enabled,
            inputPrice: model.input_cost_per_million?.toString() ?? "",
            outputPrice: model.output_cost_per_million?.toString() ?? "",
          }
        : modelDefault,
    );
    setView("model");
    if (!model) void discover(provider);
  }
  function showTests(model: Model) {
    close();
    setProviderId(model.provider_id);
    setModelId(model.model_id);
    setChecks({
      completion: model.readiness.completion,
      tool_call: model.readiness.tool_call,
    });
    setView("test");
  }
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setFailure("");
    setNotice("");
    try {
      await work();
    } catch (error) {
      setFailure((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function saveService(event: FormEvent) {
    event.preventDefault();
    if (
      !service.noKey &&
      !/^[A-Za-z_][A-Za-z0-9_]*$/.test(service.env.trim())
    ) {
      setFailure(
        "请填写部署配置中的变量名，例如 OPENAI_API_KEY；不要粘贴密钥或 ${} 符号。",
      );
      return;
    }
    await action(async () => {
      const saved = await modelRequest<Provider>(
        `${API}/${encodeURIComponent(providerId)}`,
        jsonWrite("PUT", {
          name: service.name.trim(),
          base_url: service.base_url.trim(),
          api_key_ref: service.noKey ? null : `${"${"}${service.env.trim()}}`,
          enabled: service.enabled,
        }),
      );
      await load();
      if (editing) {
        setView(null);
        setNotice("模型服务已保存；配置变化后需重新测试相关模型。");
      } else editModel(saved.provider_id);
    });
  }
  async function saveModel(event: FormEvent) {
    event.preventDefault();
    const prices = [form.inputPrice.trim(), form.outputPrice.trim()];
    if (
      prices.some(Boolean) &&
      (!prices.every(Boolean) ||
        prices.some(
          (value) => !Number.isFinite(Number(value)) || Number(value) < 0,
        ))
    ) {
      setFailure("请同时填写有效的输入和输出价格，或同时留空。");
      return;
    }
    if (form.max_output_tokens > form.context_window) {
      setFailure("最大输出不能超过上下文长度。");
      return;
    }
    await action(async () => {
      const { inputPrice, outputPrice, ...values } = form;
      const saved = await modelRequest<Model>(
        `${API}/models/${encodeURIComponent(modelId)}`,
        jsonWrite("PUT", {
          ...values,
          api_name: form.api_name.trim(),
          provider_id: providerId,
          input_cost_per_million: inputPrice.trim() ? Number(inputPrice) : null,
          output_cost_per_million: outputPrice.trim()
            ? Number(outputPrice)
            : null,
        }),
      );
      await load();
      setChecks({
        completion: saved.readiness.completion,
        tool_call: saved.readiness.tool_call,
      });
      setView("test");
    });
  }
  async function runTests() {
    testController.current?.abort();
    const controller = new AbortController();
    testController.current = controller;
    setTesting("普通生成");
    setFailure("");
    const next = {
      completion: null as Check | null,
      tool_call: null as Check | null,
    };
    setChecks(next);
    try {
      for (const mode of ["completion", "tool_call"] as const) {
        if (controller.signal.aborted) return;
        setTesting(mode === "completion" ? "普通生成" : "工具调用");
        next[mode] = await modelRequest<Check>(
          `${API}/models/${encodeURIComponent(modelId)}/test`,
          { ...jsonWrite("POST", { mode }), signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setChecks({ ...next });
      }
      await load(controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) setFailure((error as Error).message);
    } finally {
      if (testController.current === controller) {
        testController.current = null;
        setTesting(null);
      }
    }
  }
  async function applyModel() {
    await action(async () => {
      await modelRequest(`${API}/models/${encodeURIComponent(modelId)}/use`, {
        method: "POST",
      });
      await load();
      setNotice("已用于平台 Root。租户覆盖与模型权限仍按各租户配置生效。");
    });
  }
  async function remove(kind: "service" | "model", id: string, name: string) {
    if (
      !window.confirm(
        `确定删除${kind === "service" ? "模型服务" : "模型"}“${name}”？`,
      )
    )
      return;
    await action(async () => {
      await modelRequest(
        `${API}/${kind === "model" ? "models/" : ""}${encodeURIComponent(id)}`,
        { method: "DELETE" },
      );
      await load();
      setNotice("已删除。");
    });
  }
  async function saveRouting(event: FormEvent) {
    event.preventDefault();
    if (!routing) return;
    await action(async () => {
      await modelRequest(
        "/model-registry/settings",
        jsonWrite("PUT", {
          platform_default: routing.platform_default,
          tier_defaults: routing.tier_defaults,
        }),
      );
      await load();
      setNotice("高级路由已保存；平台 Root 的明确模型选择保持不变。");
    });
  }

  if (loading || state === "loading")
    return <Message>正在读取管理权限…</Message>;
  if (!user) return <SignInRequired />;
  if (state === "error")
    return <Message>无法读取管理权限，请刷新后重试。</Message>;
  if (!isAdmin || !isPlatform)
    return (
      <Message>
        此页面仅限平台管理员，租户管理员请在租户设置中管理模型权限。
      </Message>
    );
  const ready = activeModel?.readiness.ready === true;
  const regionBlocked =
    current?.residency_policy === "eu-strict" &&
    activeModel?.residency !== "eu";
  return (
    <main className="page-container mx-auto w-full max-w-6xl space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">模型接入</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            添加服务 → 选择模型 → 测试 → 用于 Root
            对话。单模型无需配置层级映射。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className={buttonClass} href="/admin">
            管理总览
          </Link>
          {!view && (
            <button
              className={buttonClass}
              disabled={dataLoading || !registry?.writable}
              onClick={() => newService()}
            >
              添加模型服务
            </button>
          )}
        </div>
      </header>
      {loadError ? (
        <div role="alert" className="glass-panel border-destructive p-4">
          {loadError}{" "}
          <button
            className={buttonClass}
            onClick={() => setReload((value) => value + 1)}
          >
            重新加载
          </button>
        </div>
      ) : dataLoading ? (
        <p role="status">正在读取模型配置…</p>
      ) : (
        <>
          <section
            aria-label="当前模型"
            className="break-words glass-panel bg-muted/20 p-4 text-sm"
          >
            <p>
              平台 Root 默认模型：
              <strong>
                {current?.root_api_name || current?.root_model || "未选择"}
              </strong>
            </p>
            <p className="mt-2 text-muted-foreground">
              当前账号所在租户：{current?.tenant_api_name || "未解析到可用模型"}
              {current?.tenant_allowed
                ? ""
                : "（尚不可用于对话，请核对租户开通状态和模型权限）"}
              。平台选择不会覆盖租户自己的模型设置和白名单。
            </p>
            <Link
              className="mt-2 inline-block text-primary underline"
              href="/agent"
            >
              查看 Root 配置
            </Link>
          </section>
          {!registry?.writable && (
            <p role="alert" className="glass-panel p-4 text-sm">
              当前由配置文件管理模型。使用数据库管理模式后才能在此新增、编辑与应用模型。
            </p>
          )}
          {notice && (
            <p role="status" className="glass-panel p-3 text-sm">
              {notice}
            </p>
          )}
          {failure && (
            <p
              role="alert"
              className="glass-panel border-destructive p-3 text-sm text-destructive"
            >
              {failure}
            </p>
          )}
          {view ? (
            <section
              aria-label="模型配置流程"
              className="mx-auto max-w-3xl glass-panel p-4 sm:p-6"
            >
              <div className="mb-5 flex items-center justify-between gap-3">
                <p className="text-xs text-muted-foreground">
                  {view === "service"
                    ? "第 1 步：添加服务"
                    : view === "model"
                      ? "第 2 步：选择模型"
                      : "第 3 步：测试并使用"}
                </p>
                <button className={buttonClass} disabled={busy} onClick={close}>
                  返回服务列表
                </button>
              </div>
              <h2
                ref={editorHeading}
                tabIndex={-1}
                className="mb-4 text-lg font-medium outline-none"
              >
                {view === "service"
                  ? editing
                    ? "编辑模型服务"
                    : "添加模型服务"
                  : view === "model"
                    ? editing
                      ? "编辑模型"
                      : "选择模型"
                    : activeModel?.api_name || "模型测试"}
              </h2>
              {view === "service" ? (
                <form
                  onSubmit={(event) => void saveService(event)}
                  className="space-y-4"
                >
                  <Field label="服务名称">
                    <input
                      required
                      className={fieldClass}
                      value={service.name}
                      onChange={(event) =>
                        setService({ ...service, name: event.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="API 根地址"
                    help="填写服务商提供的 API 前缀，通常以 /v1 结尾；不要填写完整 /chat/completions 地址。"
                  >
                    <input
                      required
                      type="url"
                      placeholder="https://api.example.com/v1"
                      className={fieldClass}
                      value={service.base_url}
                      onChange={(event) =>
                        setService({ ...service, base_url: event.target.value })
                      }
                    />
                  </Field>
                  <Field
                    label="后端密钥变量名"
                    help="例如在部署的 .env 中填写 OPENAI_API_KEY=真实密钥，再执行 docker compose up -d backend 应用配置。这里只填变量名，不填密钥本身。"
                  >
                    <input
                      disabled={service.noKey}
                      required={!service.noKey}
                      className={fieldClass}
                      value={service.env}
                      autoComplete="off"
                      onChange={(event) =>
                        setService({ ...service, env: event.target.value })
                      }
                    />
                  </Field>
                  <Toggle
                    label="该服务自身不需要密钥"
                    value={service.noKey}
                    change={(value) => setService({ ...service, noKey: value })}
                  />
                  <details className="rounded-md border p-3 text-sm">
                    <summary className="cursor-pointer">
                      高级：服务状态与标识
                    </summary>
                    <div className="mt-3 space-y-3">
                      <Toggle
                        label="启用模型服务"
                        value={service.enabled}
                        change={(value) =>
                          setService({ ...service, enabled: value })
                        }
                      />
                      <p className="break-all text-xs text-muted-foreground">
                        内部标识自动生成：{providerId}
                      </p>
                    </div>
                  </details>
                  <button
                    disabled={busy}
                    className={`${buttonClass} button-primary`}
                    type="submit"
                  >
                    {busy
                      ? "正在保存…"
                      : editing
                        ? "保存服务"
                        : "保存并选择模型"}
                  </button>
                </form>
              ) : view === "model" ? (
                <form
                  onSubmit={(event) => void saveModel(event)}
                  className="space-y-4"
                >
                  <p className="break-all text-sm text-muted-foreground">
                    所属服务：{activeProvider?.name || providerId}
                  </p>
                  <div className="glass-panel p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm">从服务读取模型</p>
                      <button
                        type="button"
                        className={buttonClass}
                        disabled={discovering}
                        onClick={() => void discover(providerId)}
                      >
                        重新读取列表
                      </button>
                    </div>
                    {discovering ? (
                      <p role="status" className="mt-2 text-sm">
                        正在读取；也可以直接手动填写下方模型名称。
                      </p>
                    ) : discovery?.ok ? (
                      <>
                        <input
                          aria-label="筛选服务模型"
                          className={fieldClass}
                          placeholder="搜索模型名称"
                          value={discoverQuery}
                          onChange={(event) =>
                            setDiscoverQuery(event.target.value)
                          }
                        />
                        <select
                          aria-label="服务返回的模型"
                          className={fieldClass}
                          value=""
                          onChange={(event) =>
                            setForm({ ...form, api_name: event.target.value })
                          }
                        >
                          <option value="">选择模型，或在下方手动填写</option>
                          {discovery.models
                            .filter((name) =>
                              name
                                .toLowerCase()
                                .includes(discoverQuery.toLowerCase()),
                            )
                            .map((name) => (
                              <option value={name} key={name}>
                                {name}
                              </option>
                            ))}
                        </select>
                        <p className="mt-2 text-xs text-muted-foreground">
                          读取列表不代表实际调用可用，下一步还会测试生成和工具调用。
                        </p>
                      </>
                    ) : (
                      discovery && (
                        <p role="status" className="mt-2 text-sm">
                          {discovery.message ||
                            "服务没有提供可读取的模型列表。"}{" "}
                          可手动填写模型名称继续。
                        </p>
                      )
                    )}
                  </div>
                  <Field
                    label="服务中的模型名称"
                    help="与服务商提供的名称逐字一致。平台内部标识会自动生成。"
                  >
                    <input
                      required
                      maxLength={256}
                      className={fieldClass}
                      value={form.api_name}
                      onChange={(event) =>
                        setForm({ ...form, api_name: event.target.value })
                      }
                    />
                  </Field>
                  <details className="rounded-md border p-3 text-sm">
                    <summary className="cursor-pointer">
                      高级：能力、限制与费用
                    </summary>
                    <div className="mt-4 space-y-4">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <Field label="上下文长度（token）">
                          <input
                            required
                            type="number"
                            min="1"
                            className={fieldClass}
                            value={form.context_window}
                            onChange={(event) =>
                              setForm({
                                ...form,
                                context_window: Number(event.target.value),
                              })
                            }
                          />
                        </Field>
                        <Field label="最大输出（token）">
                          <input
                            required
                            type="number"
                            min="1"
                            className={fieldClass}
                            value={form.max_output_tokens}
                            onChange={(event) =>
                              setForm({
                                ...form,
                                max_output_tokens: Number(event.target.value),
                              })
                            }
                          />
                        </Field>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        请按服务实际限制调整；模型列表通常不提供这些参数。
                      </p>
                      {(
                        [
                          ["supports_tools", "支持工具调用"],
                          ["supports_reasoning", "使用推理模型参数"],
                          ["supports_responses_api", "使用 Responses 接口"],
                          ["supports_vision", "支持图片输入"],
                          ["enabled", "启用模型"],
                        ] as const
                      ).map(([key, label]) => (
                        <Toggle
                          key={key}
                          label={label}
                          value={form[key]}
                          change={(value) => setForm({ ...form, [key]: value })}
                        />
                      ))}
                      <p className="text-xs text-muted-foreground">
                        Root
                        需要结构化工具调用。图片能力由服务声明，本页不会把普通文本测试当作图片能力验收。
                      </p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        <Field label="模型用途分类">
                          <select
                            className={fieldClass}
                            value={form.tier}
                            onChange={(event) =>
                              setForm({
                                ...form,
                                tier: event.target.value as Model["tier"],
                              })
                            }
                          >
                            <option value="default">日常使用</option>
                            <option value="smart">复杂分析</option>
                            <option value="fast">快速响应</option>
                          </select>
                        </Field>
                        <Field label="数据处理区域">
                          <select
                            className={fieldClass}
                            value={form.residency}
                            onChange={(event) =>
                              setForm({
                                ...form,
                                residency: event.target
                                  .value as Model["residency"],
                              })
                            }
                          >
                            <option value="global">全球</option>
                            <option value="eu">欧盟</option>
                            <option value="us">美国</option>
                          </select>
                        </Field>
                        <Field label="输入价格（美元/百万 token）">
                          <input
                            type="number"
                            min="0"
                            step="any"
                            className={fieldClass}
                            value={form.inputPrice}
                            onChange={(event) =>
                              setForm({
                                ...form,
                                inputPrice: event.target.value,
                              })
                            }
                          />
                        </Field>
                        <Field label="输出价格（美元/百万 token）">
                          <input
                            type="number"
                            min="0"
                            step="any"
                            className={fieldClass}
                            value={form.outputPrice}
                            onChange={(event) =>
                              setForm({
                                ...form,
                                outputPrice: event.target.value,
                              })
                            }
                          />
                        </Field>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        开启费用控制前需配置价格；留空表示价格未知，不表示免费。
                      </p>
                      <Field label="模型说明">
                        <textarea
                          className={fieldClass}
                          value={form.description}
                          onChange={(event) =>
                            setForm({
                              ...form,
                              description: event.target.value,
                            })
                          }
                        />
                      </Field>
                      <p className="break-all text-xs text-muted-foreground">
                        内部标识：{modelId}
                      </p>
                    </div>
                  </details>
                  <button
                    type="submit"
                    className={`${buttonClass} button-primary`}
                    disabled={busy}
                  >
                    {busy ? "正在保存…" : "保存并测试"}
                  </button>
                </form>
              ) : (
                <div className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    同一份当前配置通过两项测试后，可用于平台 Root。结果在 24
                    小时内有效；修改地址、密钥、模型名称或调用参数后需要重测。
                  </p>
                  {regionBlocked && (
                    <p
                      role="alert"
                      className="rounded-md border border-destructive p-3 text-sm"
                    >
                      此部署仅允许欧盟区域模型。当前模型区域不符合要求，请核对服务实际处理区域后修改配置；不能仅修改标签绕过。
                    </p>
                  )}
                  <ProbeCard
                    title="普通生成"
                    check={checks.completion}
                    running={testing === "普通生成"}
                  />
                  <ProbeCard
                    title="工具调用"
                    check={checks.tool_call}
                    running={testing === "工具调用"}
                  />
                  <div className="flex flex-wrap gap-2">
                    {testing ? (
                      <button
                        className={buttonClass}
                        onClick={() => {
                          testController.current?.abort();
                          setTesting(null);
                          setNotice("测试已停止；未完成的项目不算通过。");
                        }}
                      >
                        停止等待
                      </button>
                    ) : (
                      <button
                        className={buttonClass}
                        disabled={busy}
                        onClick={() => void runTests()}
                      >
                        运行两项测试
                      </button>
                    )}
                    <button
                      className={buttonClass}
                      disabled={
                        busy ||
                        !!testing ||
                        !ready ||
                        regionBlocked ||
                        current?.root_model === modelId
                      }
                      onClick={() => void applyModel()}
                    >
                      {current?.root_model === modelId
                        ? "已用于平台 Root"
                        : "用于平台 Root"}
                    </button>
                    <button
                      className={buttonClass}
                      disabled={busy || !!testing || !activeModel}
                      onClick={() =>
                        activeModel && editModel(providerId, activeModel)
                      }
                    >
                      修改模型配置
                    </button>
                  </div>
                  {ready &&
                    current?.root_model === modelId &&
                    (current.tenant_allowed ? (
                      <Link
                        href="/chat/root-agent"
                        className="inline-block button-primary px-4 py-2 text-sm "
                      >
                        开始对话
                      </Link>
                    ) : (
                      <p role="status" className="text-sm">
                        平台模型已选择；当前账号所在租户仍需开通或授权该模型。
                        <Link
                          className="ml-1 text-primary underline"
                          href="/admin/tenants"
                        >
                          检查租户配置
                        </Link>
                      </p>
                    ))}
                </div>
              )}
            </section>
          ) : (
            <>
              {providers.length === 0 ? (
                <section className="glass-panel border-dashed p-8 text-center">
                  <h2 className="font-medium">先添加一个模型服务</h2>
                  <p className="mx-auto mt-3 max-w-xl text-sm text-muted-foreground">
                    准备 API
                    地址、部署密钥变量和模型名称。点击上方“添加模型服务”，按步骤完成测试即可用于
                    Root。
                  </p>
                </section>
              ) : (
                providers.map((provider) => (
                  <section
                    key={provider.provider_id}
                    className="glass-panel p-4 sm:p-5"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h2 className="break-all font-medium">
                          {provider.name}{" "}
                          <span className="text-xs font-normal text-muted-foreground">
                            {provider.enabled ? "已启用" : "已停用"}
                          </span>
                        </h2>
                        <p className="mt-1 break-all text-xs text-muted-foreground">
                          {provider.base_url}
                        </p>
                        <p className="mt-2 text-xs">
                          {!provider.api_key_ref
                            ? "服务未要求密钥"
                            : provider.has_api_key
                              ? "后端密钥已就绪"
                              : `缺少后端密钥变量 ${provider.api_key_ref.replace(/^\$\{(.+)\}$/, "$1")}`}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          className={buttonClass}
                          disabled={
                            busy || !registry?.writable || !provider.enabled
                          }
                          onClick={() => editModel(provider.provider_id)}
                        >
                          添加模型
                        </button>
                        <button
                          className={buttonClass}
                          disabled={busy || !registry?.writable}
                          onClick={() => newService(provider)}
                        >
                          编辑服务
                        </button>
                        <button
                          className={buttonClass}
                          disabled={busy || !registry?.writable}
                          onClick={() =>
                            void remove(
                              "service",
                              provider.provider_id,
                              provider.name,
                            )
                          }
                        >
                          删除服务
                        </button>
                      </div>
                    </div>
                    <ul className="mt-4 divide-y border-t">
                      {models
                        .filter(
                          (model) => model.provider_id === provider.provider_id,
                        )
                        .map((model) => (
                          <li
                            key={model.model_id}
                            className="flex flex-wrap items-center justify-between gap-3 py-3"
                          >
                            <div className="min-w-0">
                              <h3 className="break-all text-sm font-medium">
                                {model.api_name}
                              </h3>
                              <p className="mt-1 text-xs text-muted-foreground">
                                {!model.enabled
                                  ? "已停用"
                                  : model.readiness.ready
                                    ? "测试通过，配置可供 Root 使用"
                                    : "尚未通过当前配置测试"}
                                {current?.root_model === model.model_id
                                  ? " · 平台 Root 当前模型"
                                  : ""}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <button
                                className={buttonClass}
                                disabled={
                                  busy ||
                                  !model.enabled ||
                                  !provider.enabled ||
                                  !registry?.writable
                                }
                                onClick={() => showTests(model)}
                              >
                                测试与使用
                              </button>
                              <button
                                className={buttonClass}
                                disabled={busy || !registry?.writable}
                                onClick={() =>
                                  editModel(provider.provider_id, model)
                                }
                              >
                                编辑模型
                              </button>
                              <button
                                className={buttonClass}
                                disabled={busy || !registry?.writable}
                                onClick={() =>
                                  void remove(
                                    "model",
                                    model.model_id,
                                    model.api_name,
                                  )
                                }
                              >
                                删除模型
                              </button>
                            </div>
                          </li>
                        ))}
                    </ul>
                    {!models.some(
                      (model) => model.provider_id === provider.provider_id,
                    ) && (
                      <p className="mt-3 text-sm text-muted-foreground">
                        尚未添加模型，请先从此服务选择或手动填写一个模型。
                      </p>
                    )}
                  </section>
                ))
              )}
              <details className="glass-panel p-4">
                <summary className="cursor-pointer font-medium">
                  高级：多模型路由
                </summary>
                <p className="mt-3 text-sm text-muted-foreground">
                  只有明确使用用途别名的调用才会读取这些设置，不会覆盖已选定的
                  Root 模型。单模型接入可直接忽略此区域。
                </p>
                {routing && (
                  <form
                    onSubmit={(event) => void saveRouting(event)}
                    className="mt-4 space-y-4"
                  >
                    <div className="grid gap-3 sm:grid-cols-2">
                      {(
                        [
                          ["platform_default", "后台默认模型"],
                          ["default", "日常使用（default）"],
                          ["smart", "复杂分析（smart）"],
                          ["fast", "快速响应（fast）"],
                        ] as const
                      ).map(([key, label]) => (
                        <Field key={key} label={label}>
                          <select
                            required
                            className={fieldClass}
                            value={
                              key === "platform_default"
                                ? routing.platform_default
                                : routing.tier_defaults[key]
                            }
                            onChange={(event) =>
                              setRouting(
                                key === "platform_default"
                                  ? {
                                      ...routing,
                                      platform_default: event.target.value,
                                    }
                                  : {
                                      ...routing,
                                      tier_defaults: {
                                        ...routing.tier_defaults,
                                        [key]: event.target.value,
                                      },
                                    },
                              )
                            }
                          >
                            {registry?.available_models.map((model) => (
                              <option
                                key={model.model_id}
                                value={model.model_id}
                              >
                                {model.api_name} · {model.model_id}
                              </option>
                            ))}
                          </select>
                        </Field>
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      例如：使用 smart
                      别名的分析任务会调用“复杂分析”所选模型；这不是自动判断问题难度的开关。
                    </p>
                    <button
                      className={buttonClass}
                      type="submit"
                      disabled={busy || !registry?.writable}
                    >
                      保存高级路由
                    </button>
                  </form>
                )}
              </details>
            </>
          )}
        </>
      )}
    </main>
  );
}
function Message({ children }: { children: ReactNode }) {
  return <div className="p-10 text-center text-sm">{children}</div>;
}
function Field({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: ReactNode;
}) {
  return (
    <label className="block text-sm font-medium">
      <span>{label}</span>
      {children}
      {help && (
        <span className="mt-1 block text-xs font-normal leading-relaxed text-muted-foreground">
          {help}
        </span>
      )}
    </label>
  );
}
function Toggle({
  label,
  value,
  change,
}: {
  label: string;
  value: boolean;
  change: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={value}
        onChange={(event) => change(event.target.checked)}
      />
      {label}
    </label>
  );
}
function ProbeCard({
  title,
  check,
  running,
}: {
  title: string;
  check: Check | null;
  running: boolean;
}) {
  return (
    <section className="glass-panel p-4">
      <h3 className="font-medium">
        {title}：
        {running
          ? "正在测试…"
          : !check
            ? "未测试"
            : check.ok
              ? "已通过"
              : "未通过"}
      </h3>
      {check?.latency_ms != null && (
        <p className="mt-1 text-xs text-muted-foreground">
          耗时 {check.latency_ms} 毫秒
        </p>
      )}
      {check?.tested_at && (
        <p className="mt-1 text-xs text-muted-foreground">
          测试时间：{new Date(check.tested_at * 1000).toLocaleString("zh-CN")}
        </p>
      )}
      {check && !check.ok && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {check.message} {categoryHelp[check.category || ""]}
        </p>
      )}
      {check?.content && (
        <p className="mt-2 whitespace-pre-wrap break-words text-sm">
          {check.content}
        </p>
      )}
    </section>
  );
}
