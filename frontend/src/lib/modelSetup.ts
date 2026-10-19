import { fetchWithAuth } from "@/lib/apiClient";
export const MODEL_API = "/model-providers";
export type Check = {
  ok: boolean;
  category?: string | null;
  message?: string | null;
  latency_ms?: number | null;
  tested_at?: number;
  content?: string | null;
};
export type Provider = {
  provider_id: string;
  name: string;
  base_url: string;
  api_key_ref: string | null;
  has_api_key: boolean;
  enabled: boolean;
};
export type Model = {
  model_id: string;
  api_name: string;
  provider_id: string;
  tier: "default" | "smart" | "fast";
  context_window: number;
  max_output_tokens: number;
  description: string;
  input_cost_per_million: number | null;
  output_cost_per_million: number | null;
  supports_tools: boolean;
  supports_reasoning: boolean;
  supports_responses_api: boolean;
  supports_vision: boolean;
  residency: "eu" | "us" | "global";
  enabled: boolean;
  readiness: {
    ready: boolean;
    completion: Check | null;
    tool_call: Check | null;
  };
};
export type Registry = {
  platform_default: string;
  tier_defaults: { default: string; smart: string; fast: string };
  available_models: { model_id: string; api_name: string }[];
  writable: boolean;
};
export type Current = {
  root_model: string;
  root_model_id: string | null;
  root_api_name: string | null;
  tenant_model_id: string | null;
  tenant_api_name: string | null;
  tenant_allowed: boolean;
};
export type Discovery = Check & {
  models: string[];
  model_count: number | null;
};
export function internalId(prefix: string) {
  return `${prefix}-${Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) => n.toString(16).padStart(2, "0")).join("")}`;
}
export async function modelRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetchWithAuth(`/api/proxy/api/admin${path}`, init);
  if (!response.ok) {
    let message = `请求失败（${response.status}），请重试。`;
    try {
      const { detail } = await response.json();
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail))
        message = detail.map((item) => item.msg).join("；");
    } catch {
      /* 保留代理返回的状态码。 */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export function jsonWrite(method: string, data?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  };
}
export const categoryHelp: Record<string, string> = {
  network: "检查后端能否访问 API 地址，以及代理、域名和端口。",
  authentication: "在部署配置中更新密钥，再重建 backend 服务。",
  permission: "确认密钥有该模型的访问权限。",
  model: "核对模型名称，并确保填写的是 API 根地址。",
  rate_limit: "检查服务余额、额度和请求频率后再试。",
  capability: "确认服务与模型支持结构化工具调用，检查高级能力配置。",
  schema: "检查服务是否支持所选接口格式。",
  configuration: "检查服务启用状态、密钥变量和高级模型参数。",
  protocol: "服务返回异常；可手动添加模型并验证实际调用。",
};
