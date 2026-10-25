import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentReadiness } from "../AgentReadiness";

const fetchMock = vi.fn();
vi.mock("@/lib/apiClient", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchMock(...args),
}));
let locale = "en";
vi.mock("@/contexts/I18nContext", () => ({ useI18n: () => ({ locale }) }));

const platformEndpoint = "/api/proxy/api/admin/platform-config";
const modelsEndpoint = "/api/proxy/api/admin/model-providers/models";
const currentEndpoint = `${modelsEndpoint}/current`;
let platform: unknown;
let current: Record<string, unknown>;
let models: Record<string, unknown>[];
const response = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});
const rootSection = () => screen.getByRole("region", { name: "Root configuration" });
const modelSection = () => screen.getByRole("region", { name: "Model validation" });
async function settled() {
  await waitFor(() => expect(screen.queryAllByText("Loading live configuration…")).toHaveLength(0));
}

beforeEach(() => {
  locale = "en";
  platform = {
    enabled: false,
    agent: { model: "smart", skills: ["one", "two"], tools: [], mcpServers: ["mcp"], knowledge: ["k1", "k2", "k3"] },
  };
  current = { root_model: "smart", root_model_id: "model-1", root_api_name: "real-api-model", allowed: true };
  models = [{
    model_id: "model-1",
    enabled: true,
    readiness: { ready: true, completion: { ok: true }, tool_call: { ok: true } },
  }];
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (url: string) => {
    if (url === platformEndpoint) return response(platform);
    if (url === currentEndpoint) return response(current);
    if (url === modelsEndpoint) return response(models);
    throw new Error(`Unexpected endpoint: ${url}`);
  });
});

describe("AgentReadiness", () => {
  it("shows loading without invented defaults, then renders only actual fields", async () => {
    let resolvePlatform!: (value: ReturnType<typeof response>) => void;
    const pending = new Promise<ReturnType<typeof response>>((resolve) => { resolvePlatform = resolve; });
    fetchMock.mockImplementation((url: string) => url === platformEndpoint ? pending : Promise.resolve(response(url === currentEndpoint ? current : models)));
    render(<AgentReadiness />);
    expect(within(rootSection()).getByRole("status")).toHaveTextContent("Loading live configuration");
    expect(within(rootSection()).queryByText("Bound: 0")).toBeNull();
    expect(within(rootSection()).getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Both model checks passed/)).toBeNull();
    await act(async () => resolvePlatform(response(platform)));
    await settled();
    expect(within(rootSection()).getByText("smart")).toBeInTheDocument();
    expect(within(rootSection()).getByText("Disabled")).toBeInTheDocument();
    for (const count of [0, 1, 2, 3]) expect(within(rootSection()).getByText(`Bound: ${count}`)).toBeInTheDocument();
    expect(within(modelSection()).getByText("model-1 / real-api-model")).toBeInTheDocument();
    expect(within(modelSection()).getByText("Enabled")).toBeInTheDocument();
    expect(within(modelSection()).getAllByText("Passed")).toHaveLength(2);
    expect(screen.getByText(/^Both model checks passed; target-account/)).toBeInTheDocument();
    expect(screen.getByText(/Binding counts do not imply availability or authorization/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([platformEndpoint, currentEndpoint, modelsEndpoint]);
    expect(fetchMock.mock.calls.every(([, init]) => !init.method || init.method === "GET")).toBe(true);
  });

  it("provides the existing setup and target-account workflow, without an acceptance button", async () => {
    render(<AgentReadiness />);
    await settled();
    const steps = screen.getByText("Setup and validation steps");
    expect(steps.closest("details")).not.toHaveAttribute("open");
    fireEvent.click(steps);
    expect(screen.getByRole("link", { name: "Verify in workspace" })).toHaveAttribute("href", "/chat/root-agent");
    expect(screen.getByRole("link", { name: "Confirm model application" })).toHaveAttribute("href", "/admin/model-providers");
    expect(screen.getByRole("link", { name: "Confirm shared bindings" })).toHaveAttribute("href", "/agent");
    for (const name of ["Skills", "Tools", "MCP", "Knowledge"]) {
      expect(screen.getByRole("link", { name: `Configure ${name}` })).toHaveAttribute("href", "/agent");
    }
    expect(screen.getByRole("link", { name: "Review user access" })).toHaveAttribute("href", "/admin/users");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it.each([
    ["missing readiness", { enabled: true }],
    ["ready flag alone", { enabled: true, readiness: { ready: true } }],
    ["failed generation", { enabled: true, readiness: { ready: false, completion: { ok: false }, tool_call: { ok: true } } }],
    ["unverified tools", { enabled: true, readiness: { ready: false, completion: { ok: true }, tool_call: null } }],
    ["disabled model", { enabled: false, readiness: { ready: true, completion: { ok: true }, tool_call: { ok: true } } }],
    ["unknown enabled state", { readiness: { ready: true, completion: { ok: true }, tool_call: { ok: true } } }],
  ])("does not claim readiness for %s", async (_label, fields) => {
    models = [{ model_id: "model-1", ...fields }];
    render(<AgentReadiness />);
    await settled();
    expect(screen.getByText("Model selected, pending validation")).toBeInTheDocument();
    expect(screen.queryByText(/^Both model checks passed/)).toBeNull();
    if (_label === "failed generation") expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it.each([false, undefined])("does not confuse allowed=%s with verification", async (allowed) => {
    current.allowed = allowed;
    render(<AgentReadiness />);
    await settled();
    expect(screen.getByText("Model selected, pending validation")).toBeInTheDocument();
  });

  it("does not use checks belonging to a different model", async () => {
    models[0].model_id = "other-model";
    render(<AgentReadiness />);
    await settled();
    expect(screen.getByText("Model selected, pending validation")).toBeInTheDocument();
    expect(screen.getAllByText("Not verified")).toHaveLength(2);
  });

  it("does not claim readiness when configuration and resolution disagree", async () => {
    current.root_model = "other-alias";
    render(<AgentReadiness />);
    await settled();
    expect(screen.getByText(/Configured and resolved models differ/)).toBeInTheDocument();
    expect(screen.getByText("Model selected, pending validation")).toBeInTheDocument();
  });

  it("keeps absent or malformed fields unknown rather than normalizing defaults", async () => {
    platform = { agent: { skills: null, tools: {}, mcpServers: [5] } };
    current = {};
    models = [];
    render(<AgentReadiness />);
    await settled();
    expect(within(rootSection()).getAllByText("Bound: Unknown")).toHaveLength(4);
    expect(within(rootSection()).queryByText("smart")).toBeNull();
    expect(within(rootSection()).queryByText("Enabled")).toBeNull();
    expect(screen.getByText("Model state unknown; review required")).toBeInTheDocument();
    expect(screen.getAllByText("Not verified")).toHaveLength(2);
  });

  it.each([platformEndpoint, currentEndpoint, modelsEndpoint])("retries only the failed resource %s", async (failedEndpoint) => {
    const implementation = fetchMock.getMockImplementation()!;
    let failed = true;
    fetchMock.mockImplementation((url: string, init: RequestInit) => failed && url === failedEndpoint
      ? Promise.reject(new Error("offline")) : implementation(url, init));
    render(<AgentReadiness />);
    await settled();
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load configuration.");
    expect(screen.queryByText(/^Both model checks passed/)).toBeNull();
    if (failedEndpoint !== platformEndpoint) expect(within(rootSection()).getByText("Bound: 2")).toBeInTheDocument();
    failed = false;
    fetchMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await settled();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(failedEndpoint);
    expect(screen.getByText(/^Both model checks passed/)).toBeInTheDocument();
  });

  it.each([401, 403])("shows an explicit permission error for HTTP %s", async (status) => {
    fetchMock.mockResolvedValue(response({}, status));
    render(<AgentReadiness />);
    await settled();
    expect(screen.getAllByRole("alert")).toHaveLength(3);
    expect(screen.getAllByText("You do not have access to this configuration.")).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(3);
    expect(screen.queryByText("Bound: 0")).toBeNull();
  });

  it("keeps successful configuration through another resource's failed retry and language change", async () => {
    const implementation = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url: string, init: RequestInit) => url === modelsEndpoint
      ? Promise.resolve(response({}, 503)) : implementation(url, init));
    const { rerender } = render(<AgentReadiness />);
    await settled();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await settled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(within(rootSection()).getByText("Bound: 2")).toBeInTheDocument();
    expect(within(modelSection()).getByText("model-1 / real-api-model")).toBeInTheDocument();
    fetchMock.mockImplementation(implementation);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await settled();
    expect(screen.getByText(/^Both model checks passed/)).toBeInTheDocument();
    // 现有组件无自动刷新；通过 locale 重渲染确认已读取配置不会被默认值覆盖。
    locale = "zh-CN";
    rerender(<AgentReadiness />);
    expect(screen.getByText("已绑定：2")).toBeInTheDocument();
    expect(screen.getByText("当前模型双测试已通过，仍需用目标账号验证")).toBeInTheDocument();
    expect(screen.queryByText("模型已选择，待验证")).toBeNull();
  });

  it("treats malformed response envelopes as retryable errors", async () => {
    fetchMock.mockResolvedValue(response(null));
    render(<AgentReadiness />);
    await settled();
    expect(screen.getAllByRole("alert")).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(3);
  });

  it("renders a Chinese load error with a working local retry", async () => {
    locale = "zh-CN";
    const implementation = fetchMock.getMockImplementation()!;
    fetchMock.mockResolvedValue(response({}, 503));
    render(<AgentReadiness />);
    await waitFor(() => expect(screen.getAllByRole("button", { name: "重试" })).toHaveLength(3));
    expect(screen.getAllByText("读取失败。")).toHaveLength(3);
    fetchMock.mockImplementation(implementation);
    fireEvent.click(screen.getAllByRole("button", { name: "重试" })[0]);
    await waitFor(() => expect(screen.getByText("已绑定：2")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: "重试" })).toHaveLength(2);
    expect(screen.getByText("模型已选择，待验证")).toBeInTheDocument();
  });

  it("renders Chinese copy and conservative model status", async () => {
    locale = "zh-CN";
    delete models[0].readiness;
    render(<AgentReadiness />);
    await waitFor(() => expect(screen.queryAllByText("正在读取真实配置…")).toHaveLength(0));
    expect(screen.getByRole("heading", { name: "Agent 就绪清单" })).toBeInTheDocument();
    expect(screen.getByText("模型已选择，待验证")).toBeInTheDocument();
    expect(screen.getByText("已绑定：2")).toBeInTheDocument();
    expect(screen.getByText("绑定数量不代表可用或授权；实际访问仍由后端按目标用户校验。")).toBeInTheDocument();
    fireEvent.click(screen.getByText("配置与验证步骤"));
    expect(screen.getByRole("link", { name: "前往工作台验证" })).toHaveAttribute("href", "/chat/root-agent");
  });
});
