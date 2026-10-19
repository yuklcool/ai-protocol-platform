import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import ModelProvidersPage from "../page";
const { fetcher, scope, auth } = vi.hoisted(() => ({
  fetcher: vi.fn(),
  scope: { state: "platform", isAdmin: true, isPlatform: true },
  auth: { user: { uid: "admin" }, loading: false },
}));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: fetcher }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/hooks/useAdminScope", () => ({ useAdminScope: () => scope }));
vi.mock("@/components/chat/SignInRequired", () => ({
  SignInRequired: () => <div>请登录</div>,
}));
const API = "/api/proxy/api/admin/model-providers";
const SETTINGS = "/api/proxy/api/admin/model-registry/settings";
const provider = {
  provider_id: "gateway",
  name: "我的服务",
  base_url: "https://gateway.example/v1",
  api_key_ref: "${GATEWAY_KEY}",
  has_api_key: true,
  enabled: true,
};
const check = {
  ok: true,
  message: "已通过",
  latency_ms: 30,
  tested_at: Date.now() / 1000,
};
const model = {
  model_id: "custom",
  api_name: "service-chat",
  provider_id: "gateway",
  tier: "smart",
  context_window: 128000,
  max_output_tokens: 8192,
  description: "说明",
  input_cost_per_million: 1,
  output_cost_per_million: 2,
  supports_tools: true,
  supports_reasoning: false,
  supports_responses_api: false,
  supports_vision: false,
  residency: "eu",
  enabled: true,
  readiness: { ready: false, completion: null, tool_call: null },
};
let rows: (typeof model)[];
let services: (typeof provider)[];
let root: string;
let ready: boolean;
let passed: Set<string>;
function reply(value: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => value };
}
beforeEach(() => {
  rows = [{ ...model }];
  services = [{ ...provider }];
  root = "lite";
  ready = false;
  passed = new Set();
  scope.isPlatform = true;
  fetcher.mockReset();
  fetcher.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT" && url.startsWith(API + "/models/")) {
      const data = JSON.parse(String(init.body));
      const id = url.split("/").pop();
      rows = [
        {
          ...model,
          ...data,
          model_id: id,
          readiness: { ready: false, completion: null, tool_call: null },
        },
      ];
      return reply(rows[0]);
    }
    if (
      init?.method === "PUT" &&
      url.startsWith(API + "/") &&
      !url.includes("/models")
    ) {
      const data = JSON.parse(String(init.body));
      services = [{ ...provider, ...data, provider_id: url.split("/").pop() }];
      return reply(services[0]);
    }
    if (url.endsWith("/use")) {
      root = "custom";
      return reply({ root_model: root });
    }
    if (url.endsWith("/test") && url.includes("/models/")) {
      passed.add(JSON.parse(String(init?.body)).mode);
      ready = passed.has("completion") && passed.has("tool_call");
      return reply(check);
    }
    if (url.endsWith("/test"))
      return reply({ ok: true, models: ["discovered-chat"], model_count: 1 });
    if (url === API) return reply(services);
    if (url === API + "/models")
      return reply(
        rows.map((row) => ({
          ...row,
          readiness: ready
            ? { ready: true, completion: check, tool_call: check }
            : row.readiness,
        })),
      );
    if (url === SETTINGS)
      return reply({
        platform_default: "custom",
        tier_defaults: { default: "custom", smart: "custom", fast: "custom" },
        available_models: [{ model_id: "custom", api_name: "service-chat" }],
        writable: true,
      });
    if (url.endsWith("/current"))
      return reply({
        root_model: root,
        root_api_name: root === "custom" ? "service-chat" : "预置模型",
        root_model_id: root,
        tenant_model_id: root,
        tenant_api_name: "当前租户模型",
        tenant_allowed: true,
      });
    return reply({});
  });
});
async function open() {
  render(<ModelProvidersPage />);
  await screen.findByRole("heading", { name: /我的服务/ });
}
it("租户管理员无权读取平台模型配置", () => {
  scope.isPlatform = false;
  render(<ModelProvidersPage />);
  expect(screen.getByText(/此页面仅限平台管理员/)).toBeInTheDocument();
  expect(fetcher).not.toHaveBeenCalled();
});
it("默认只显示管理列表，高级路由折叠且没有展开编辑表单", async () => {
  await open();
  expect(
    screen.getByText("高级：多模型路由").closest("details"),
  ).not.toHaveAttribute("open");
  expect(screen.queryByLabelText("服务名称")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "保存服务" }),
  ).not.toBeInTheDocument();
});
it("首次接入自动生成 ID，通过发现选择模型而不用手填内部标识", async () => {
  services = [];
  rows = [];
  render(<ModelProvidersPage />);
  await screen.findByText("先添加一个模型服务");
  fireEvent.click(screen.getByRole("button", { name: "添加模型服务" }));
  fireEvent.change(screen.getByLabelText("服务名称"), {
    target: { value: "新服务" },
  });
  fireEvent.change(screen.getByLabelText(/^API 根地址/), {
    target: { value: "https://new.example/v1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并选择模型" }));
  await screen.findByLabelText("服务返回的模型");
  const serviceCall = fetcher.mock.calls.find(
    ([url, init]) =>
      url.match(/model-providers\/service-/) && init?.method === "PUT",
  );
  expect(serviceCall).toBeTruthy();
  expect(JSON.parse(serviceCall![1].body).api_key_ref).toBe(
    "${OPENAI_API_KEY}",
  );
  fireEvent.change(screen.getByLabelText("服务返回的模型"), {
    target: { value: "discovered-chat" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  await screen.findByRole("button", { name: "运行两项测试" });
  const call = fetcher.mock.calls.find(
    ([url, init]) => url.includes("/models/model-") && init?.method === "PUT",
  );
  expect(JSON.parse(call![1].body).api_name).toBe("discovered-chat");
  expect(
    fetcher.mock.calls.some(
      ([url, init]) => url === SETTINGS && init?.method === "PUT",
    ),
  ).toBe(false);
});
it("模型列表不支持发现时仍可手动添加", async () => {
  await open();
  fetcher.mockImplementationOnce(async () =>
    reply({
      ok: false,
      category: "protocol",
      message: "不支持模型列表",
      models: [],
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "添加模型" }));
  await screen.findByText(/不支持模型列表/);
  const input = screen.getByLabelText(/^服务中的模型名称/);
  fireEvent.change(input, { target: { value: "manual-model" } });
  expect(input).toHaveValue("manual-model");
});
it("编辑服务保留已配置的密钥变量，不把引用当成密钥输入", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "编辑服务" }));
  expect(screen.getByLabelText(/^后端密钥变量名/)).toHaveValue("GATEWAY_KEY");
  fireEvent.click(screen.getByRole("button", { name: "保存服务" }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      API + "/gateway",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  const call = fetcher.mock.calls.find(
    ([url, init]) => url === API + "/gateway" && init?.method === "PUT",
  )!;
  expect(JSON.parse(call[1].body).api_key_ref).toBe("${GATEWAY_KEY}");
});
it("编辑模型保留费用和能力设置，不能静默丢配置", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "编辑模型" }));
  expect(screen.getByLabelText("输入价格（美元/百万 token）")).toHaveValue(1);
  fireEvent.change(screen.getByLabelText("数据处理区域"), {
    target: { value: "us" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      API + "/models/custom",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  const call = fetcher.mock.calls.find(
    ([url, init]) => url === API + "/models/custom" && init?.method === "PUT",
  )!;
  expect(JSON.parse(call[1].body)).toMatchObject({
    tier: "smart",
    residency: "us",
    input_cost_per_million: 1,
    output_cost_per_million: 2,
  });
});
it("两项测试集中展示，通过后才能明确用于平台 Root", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "测试与使用" }));
  expect(screen.getByRole("button", { name: "用于平台 Root" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "运行两项测试" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "用于平台 Root" })).toBeEnabled(),
  );
  expect(fetcher).toHaveBeenCalledWith(
    API + "/models/custom/test",
    expect.objectContaining({ body: JSON.stringify({ mode: "completion" }) }),
  );
  expect(fetcher).toHaveBeenCalledWith(
    API + "/models/custom/test",
    expect.objectContaining({ body: JSON.stringify({ mode: "tool_call" }) }),
  );
  fireEvent.click(screen.getByRole("button", { name: "用于平台 Root" }));
  await screen.findByRole("link", { name: "开始对话" });
  expect(fetcher).toHaveBeenCalledWith(API + "/models/custom/use", {
    method: "POST",
  });
});
it("测试失败给出中文修复提示，不显示原始 JSON", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "测试与使用" }));
  fetcher.mockResolvedValueOnce(
    reply({ ok: false, category: "authentication", message: "密钥无效" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "运行两项测试" }));
  await screen.findByText(/密钥无效/);
  expect(screen.getByText(/在部署配置中更新密钥/)).toBeInTheDocument();
  expect(document.querySelector("pre")).toBeNull();
});
it("加载失败可以重试，不能显示未配置的假空状态", async () => {
  fetcher.mockRejectedValueOnce(new Error("后端不可达"));
  render(<ModelProvidersPage />);
  await screen.findByText("后端不可达");
  expect(screen.queryByText("先添加一个模型服务")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await screen.findByRole("heading", { name: /我的服务/ });
});
it("保存失败保留填写内容并解除禁用", async () => {
  await open();
  fireEvent.click(screen.getByRole("button", { name: "编辑服务" }));
  fetcher.mockRejectedValueOnce(new Error("保存失败"));
  fireEvent.click(screen.getByRole("button", { name: "保存服务" }));
  await screen.findByText("保存失败");
  expect(screen.getByRole("button", { name: "保存服务" })).toBeEnabled();
  expect(screen.getByLabelText("服务名称")).toHaveValue("我的服务");
});
