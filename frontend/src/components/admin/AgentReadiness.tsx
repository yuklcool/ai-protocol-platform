"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/contexts/I18nContext";
import { fetchWithAuth } from "@/lib/apiClient";
import { MODEL_API } from "@/lib/modelSetup";

const modelEndpoint = `/api/proxy/api/admin${MODEL_API}/models`;

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function useReadinessResource(endpoint: string, list = false) {
  const [data, setData] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<number | "network" | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const response = await fetchWithAuth(endpoint, { signal: controller.signal });
        if (!response.ok) {
          if (!controller.signal.aborted) setError(response.status);
          return;
        }
        const body: unknown = await response.json();
        if (list ? !Array.isArray(body) : body === null || typeof body !== "object" || Array.isArray(body)) {
          throw new Error("Invalid response");
        }
        if (!controller.signal.aborted) setData(body);
      } catch {
        if (!controller.signal.aborted) setError("network");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [endpoint, list, revision]);

  return { data, loading, error, retry: () => setRevision((value) => value + 1) };
}

type Resource = ReturnType<typeof useReadinessResource>;

function ReadStatus({ resource, zh }: { resource: Resource; zh: boolean }) {
  if (resource.loading) {
    return <p role="status" className="text-sm text-muted-foreground">{zh ? "正在读取真实配置…" : "Loading live configuration…"}</p>;
  }
  if (!resource.error) return null;
  return (
    <div role="alert" className="notice notice--danger mt-2 flex flex-wrap items-center gap-2">
      <span>
        {resource.error === 401 || resource.error === 403
          ? zh ? "无权限读取此配置。" : "You do not have access to this configuration."
          : zh ? "读取失败。" : "Could not load configuration."}
        {resource.data !== null && (zh ? " 保留上次读取结果，可能已过期。" : " Showing the last result; it may be stale.")}
      </span>
      <button type="button" className="button-secondary px-3 py-1.5 text-sm" onClick={resource.retry}>
        {zh ? "重试" : "Retry"}
      </button>
    </div>
  );
}

export function AgentReadiness({ onVerified }: { onVerified?: (ready: boolean) => void } = {}) {
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  const unknown = zh ? "未知" : "Unknown";
  const platform = useReadinessResource("/api/proxy/api/admin/platform-config");
  const current = useReadinessResource(`${modelEndpoint}/current`);
  const models = useReadinessResource(modelEndpoint, true);
  const config = record(platform.data);
  const agent = record(config.agent);
  const resolved = record(current.data);
  const rootModel = text(agent.model);
  const currentModel = text(resolved.root_model);
  const modelId = text(resolved.root_model_id);
  const selected = record(
    Array.isArray(models.data)
      ? models.data.find((model) => modelId && record(model).model_id === modelId)
      : undefined,
  );
  const readiness = record(selected.readiness);
  const completion = record(readiness.completion);
  const toolCall = record(readiness.tool_call);
  const consistent = !!rootModel && rootModel === currentModel;
  const verified = consistent && !platform.loading && !current.loading && !models.loading
    && !platform.error && !current.error && !models.error
    && selected.enabled === true && resolved.allowed === true
    && readiness.ready === true && completion.ok === true && toolCall.ok === true;
  useEffect(() => { onVerified?.(verified); }, [verified, onVerified]);
  const enabledLabel = (value: unknown) => value === true
    ? zh ? "已启用" : "Enabled"
    : value === false ? zh ? "已停用" : "Disabled" : unknown;
  const checkLabel = (value: unknown) => value === true
    ? zh ? "通过" : "Passed"
    : value === false ? zh ? "未通过" : "Failed" : zh ? "待验证" : "Not verified";
  const linkClass = "inline-flex min-h-11 items-center rounded-md px-2 text-sm font-medium text-primary hover:bg-primary/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring";
  const bindings = [
    ["skills", "Skills"],
    ["tools", "Tools"],
    ["mcpServers", "MCP"],
    ["knowledge", zh ? "知识库" : "Knowledge"],
  ] as const;

  return (
    <section aria-labelledby="agent-readiness-title" className="glass-panel mb-4 space-y-5 p-5">
      <div>
        <h2 id="agent-readiness-title" className="text-lg font-semibold">{zh ? "Agent 就绪清单" : "Agent readiness checklist"}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{zh ? "仅展示后端实际配置与验证记录，不代表目标用户已完成验收。" : "Live backend configuration and validation records only; target-user acceptance is still required."}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-label={zh ? "Root 配置" : "Root configuration"} className="surface-sunken min-w-0 p-4">
          <h3 className="font-medium">{zh ? "Root 配置与公共绑定" : "Root configuration & shared bindings"}</h3>
          <ReadStatus resource={platform} zh={zh} />
          <dl className="mt-3 space-y-2 text-sm">
            <div><dt className="text-muted-foreground">{zh ? "Root 模型配置" : "Configured Root model"}</dt><dd className="break-all font-mono">{rootModel ?? unknown}</dd></div>
            <div><dt className="text-muted-foreground">{zh ? "平台前置指令开关（非 Agent 启停）" : "Platform preamble switch (not Agent activation)"}</dt><dd>{enabledLabel(config.enabled)}</dd></div>
            {bindings.map(([key, label]) => {
              const value = agent[key];
              const count = Array.isArray(value) && value.every((id) => typeof id === "string") ? value.length : unknown;
              return (
                <div key={key} className="flex flex-wrap items-center justify-between gap-2">
                  <dt>{label}</dt>
                  <dd className="flex items-center gap-2">
                    <span>{zh ? `已绑定：${count}` : `Bound: ${count}`}</span>
                    <Link href="/agent" className={linkClass}>{zh ? `配置 ${label}` : `Configure ${label}`}</Link>
                  </dd>
                </div>
              );
            })}
          </dl>
          <p className="mt-2 text-xs text-muted-foreground">{zh ? "绑定数量不代表可用或授权；实际访问仍由后端按目标用户校验。" : "Binding counts do not imply availability or authorization; the backend checks access for each target user."}</p>
          <Link href="/agent" className={linkClass}>{zh ? "配置 Root Agent" : "Configure Root Agent"}</Link>
        </section>
        <section aria-label={zh ? "模型验证" : "Model validation"} className="surface-sunken min-w-0 p-4">
          <h3 className="font-medium">{zh ? "当前模型与双测试" : "Current model & both checks"}</h3>
          <div className="mt-2">
            <p className="text-xs text-muted-foreground">{zh ? "当前模型解析" : "Current model resolution"}</p>
            <ReadStatus resource={current} zh={zh} />
          </div>
          <div className="mt-2">
            <p className="text-xs text-muted-foreground">{zh ? "数据库模型验证记录" : "Database model validation records"}</p>
            <ReadStatus resource={models} zh={zh} />
          </div>
          <dl className="mt-3 space-y-2 text-sm">
            <div><dt className="text-muted-foreground">{zh ? "当前解析模型" : "Resolved Root model"}</dt><dd className="break-all font-mono">{modelId ?? unknown} / {text(resolved.root_api_name) ?? unknown}</dd></div>
            <div><dt className="text-muted-foreground">{zh ? "模型启用状态" : "Model enabled state"}</dt><dd>{enabledLabel(selected.enabled)}</dd></div>
            <div><dt className="text-muted-foreground">{zh ? "模型策略" : "Model policy"}</dt><dd>{resolved.allowed === true ? zh ? "允许（不代表已验证）" : "Allowed (not proof of validation)" : resolved.allowed === false ? zh ? "不允许" : "Not allowed" : unknown}</dd></div>
            <div><dt>{zh ? "文本生成测试" : "Text generation check"}</dt><dd>{checkLabel(completion.ok)}</dd></div>
            <div><dt>{zh ? "原生工具调用测试" : "Native tool-call check"}</dt><dd>{checkLabel(toolCall.ok)}</dd></div>
          </dl>
          {rootModel && currentModel && !consistent && <p className="notice notice--warning mt-2">{zh ? "配置与解析模型不一致，请在现有模型页面核对。" : "Configured and resolved models differ; review the existing model page."}</p>}
          <p role="status" className="mt-3 text-sm font-medium">
            {verified
              ? zh ? "当前模型双测试已通过，仍需用目标账号验证" : "Both model checks passed; target-account validation is still required"
              : rootModel || currentModel
                ? zh ? "模型已选择，待验证" : "Model selected, pending validation"
                : zh ? "模型状态未知，待核对" : "Model state unknown; review required"}
          </p>
          <Link href="/admin/model-providers" className={linkClass}>{zh ? "接入、验证与确认应用模型" : "Connect, validate & confirm model application"}</Link>
        </section>
      </div>
      <div>
        <h3 className="font-medium">{zh ? "接入 → 验证 → 确认应用 → 用目标账号验证" : "Connect → Validate → Confirm application → Verify with the target account"}</h3>
        <ol className="mt-2 list-inside list-decimal space-y-2 text-sm text-muted-foreground">
          <li>{zh ? "在现有页面接入服务与模型，管理公共能力资源。" : "Connect services and models, and manage shared resources on the existing pages."} <Link href="/admin/model-providers" className={linkClass}>{zh ? "模型接入" : "Model setup"}</Link><Link href="/skills" className={linkClass}>{zh ? "Skills 中心" : "Skills center"}</Link><Link href="/admin/mcp-servers" className={linkClass}>{zh ? "MCP 管理" : "Manage MCP"}</Link></li>
          <li>{zh ? "在模型管理页分别运行文本生成和原生工具调用测试。" : "Run text generation and native tool-call checks separately on the model page."} <Link href="/admin/model-providers" className={linkClass}>{zh ? "验证模型" : "Validate model"}</Link></li>
          <li>{zh ? "测试通过后，在原模型页面明确选用；在 Root 配置页确认绑定并保存，不自动应用。" : "After validation, explicitly select the model on its existing page; confirm and save bindings in Root settings. Nothing is applied automatically."} <Link href="/admin/model-providers" className={linkClass}>{zh ? "确认模型应用" : "Confirm model application"}</Link><Link href="/agent" className={linkClass}>{zh ? "确认公共绑定" : "Confirm shared bindings"}</Link></li>
          <li>{zh ? "切换为目标账号，在工作台发起真实任务，验证能力、授权与结果；管理员配置不等于用户验收。" : "Switch to the target account and run a real task in the workspace to verify capabilities, access and results; admin configuration is not user acceptance."} <Link href="/workspace" className={linkClass}>{zh ? "前往工作台验证" : "Verify in workspace"}</Link><Link href="/admin/users" className={linkClass}>{zh ? "核对用户权限" : "Review user access"}</Link></li>
        </ol>
      </div>
    </section>
  );
}
