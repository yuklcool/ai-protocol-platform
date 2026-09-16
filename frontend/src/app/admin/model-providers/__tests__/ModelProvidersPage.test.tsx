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
vi.mock("@/components/chat/SignInRequired", () => ({ SignInRequired: () => <div>Sign in</div> }));
const API = "/api/proxy/api/admin/model-providers";
const SETTINGS_API = "/api/proxy/api/admin/model-registry/settings";
const provider = { provider_id: "gateway", name: "Gateway", base_url: "http://gateway:8080/v1", api_key_ref: "${GATEWAY_KEY}", has_api_key: true, enabled: true };
const model = { model_id: "custom", api_name: "qwen", provider_id: "gateway", tier: "smart", context_window: 128000, max_output_tokens: 8192, description: "Custom", supports_tools: true, supports_reasoning: false, supports_responses_api: false, supports_vision: false, residency: "eu", enabled: true };
const settings = {
  platform_default: "custom",
  tier_defaults: { default: "custom", smart: "custom", fast: "custom" },
  available_models: [{ model_id: "custom", api_name: "qwen", provider: "openai", provider_id: "gateway", tier: "smart", residency: "eu", source: "database" }],
  source: "database",
  writable: true,
};
function reply(body: unknown, ok = true) { return { ok, json: async () => body }; }
beforeEach(() => {
  fetcher.mockReset();
  scope.isPlatform = true;
  fetcher.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method) {
      if (url === SETTINGS_API && init.method === "PUT") return reply(settings);
      return reply({ ok: true, tool_called: true });
    }
    if (url === API) return reply([provider]);
    if (url === `${API}/models`) return reply([model]);
    if (url === SETTINGS_API) return reply(settings);
    return reply({}, false);
  });
});
it("denies tenant admins without requesting configuration", () => {
  scope.isPlatform = false;
  render(<ModelProvidersPage />);
  expect(screen.getByText(/Platform admin required/)).toBeTruthy();
  expect(fetcher).not.toHaveBeenCalled();
});
it("edits models across tier and residency choices and sends the contract", async () => {
  render(<ModelProvidersPage />);
  await screen.findByText("custom");
  fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[1]);
  fireEvent.change(screen.getByLabelText("Model tier"), { target: { value: "fast" } });
  fireEvent.change(screen.getByLabelText("Model residency"), { target: { value: "us" } });
  fireEvent.click(screen.getByRole("button", { name: "Save model" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith(`${API}/models/custom`, expect.objectContaining({ method: "PUT" })));
  const call = fetcher.mock.calls.find(([url, init]) => url === `${API}/models/custom` && init?.method === "PUT")!;
  expect(JSON.parse(call[1].body)).toMatchObject({ tier: "fast", residency: "us", provider_id: "gateway", context_window: 128000 });
});
it("retains the secret reference on provider edits", async () => {
  render(<ModelProvidersPage />);
  await screen.findByText("custom");
  fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Save provider" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith(`${API}/gateway`, expect.objectContaining({ method: "PUT" })));
  const call = fetcher.mock.calls.find(([url, init]) => url === `${API}/gateway` && init?.method === "PUT")!;
  expect(JSON.parse(call[1].body).api_key_ref).toBe("${GATEWAY_KEY}");
});
it("saves platform default and default smart fast runtime mappings", async () => {
  render(<ModelProvidersPage />);
  await screen.findByRole("button", { name: "Save model routing" });
  expect(screen.getByLabelText("Platform default model")).toHaveValue("custom");
  expect(screen.getByLabelText("Default tier model")).toHaveValue("custom");
  expect(screen.getByLabelText("Smart tier model")).toHaveValue("custom");
  expect(screen.getByLabelText("Fast tier model")).toHaveValue("custom");

  fireEvent.click(screen.getByRole("button", { name: "Save model routing" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith(SETTINGS_API, expect.objectContaining({ method: "PUT" })));
  const call = fetcher.mock.calls.find(([url, init]) => url === SETTINGS_API && init?.method === "PUT")!;
  expect(JSON.parse(call[1].body)).toEqual({
    platform_default: "custom",
    tier_defaults: { default: "custom", smart: "custom", fast: "custom" },
  });
});
it("sends the tool calling probe and displays its outcome", async () => {
  render(<ModelProvidersPage />);
  await screen.findByText("custom");
  fireEvent.click(screen.getByRole("button", { name: "Tool call" }));
  await screen.findByText("custom · tool_call");
  expect(fetcher).toHaveBeenCalledWith(`${API}/models/custom/test`, expect.objectContaining({ body: JSON.stringify({ mode: "tool_call" }) }));
});
it("shows load and action network failures instead of unhandled rejections", async () => {
  fetcher.mockRejectedValueOnce(new Error("offline"));
  render(<ModelProvidersPage />);
  await screen.findByText(/Could not load model configuration/);
});
it("restores controls after a failed save", async () => {
  render(<ModelProvidersPage />);
  await screen.findByText("custom");
  fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
  fetcher.mockRejectedValueOnce(new Error("offline"));
  fireEvent.click(screen.getByRole("button", { name: "Save provider" }));
  await screen.findByText(/Could not save configuration/);
  expect(screen.getByRole("button", { name: "Save provider" })).not.toBeDisabled();
});
