import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RootAgentSettingsPage } from "../RootAgentSettingsPage";
import { DEFAULT_ROOT_AGENT_CONFIG } from "@/types/rootAgent";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: fetchMock }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { uid: "admin" }, loading: false }) }));

let currentModel = "smart";
const overrides = { "tenant-a": { model: "tenant-model", tools: ["tenant-tool"] } };

beforeEach(() => {
  fetchMock.mockReset();
  currentModel = "smart";
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    let body: unknown = [];
    if (url.endsWith("/platform-config")) body = init?.method === "PUT"
      ? JSON.parse(String(init.body))
      : { agent: { ...DEFAULT_ROOT_AGENT_CONFIG, model: currentModel, tenantOverrides: overrides } };
    if (url.endsWith("/models")) body = { models: [{ id: "custom-model", label: "Custom model" }] };
    if (url.endsWith("/tools")) body = { tools: [] };
    return { ok: true, status: 200, json: async () => body };
  });
});

describe("Root model selection", () => {
  it.each(["smart", "retired-model"])("shows the actual saved model %s when the registry has other models", async (model) => {
    currentModel = model;
    render(<RootAgentSettingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Model" }));
    expect(screen.getByRole("combobox", { name: "Language model" })).toHaveValue(model);
  });

  it("changes the model while preserving tenant policy overrides", async () => {
    render(<RootAgentSettingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Model" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Language model" }), { target: { value: "custom-model" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true));
    const saved = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(String(saved?.[1].body));
    expect(body.agent.model).toBe("custom-model");
    expect(body.agent.tenantOverrides).toEqual(overrides);
  });
});
