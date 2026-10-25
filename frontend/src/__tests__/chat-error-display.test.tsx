import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { StreamError, UseSkillAgentReturn } from "@/hooks/useSkillAgent";

// Minimal message list so the chat renders without needing a real AGUIProvider.
const noMessages: UseSkillAgentReturn["messages"] = [];

const mockSendMessage = vi.fn().mockResolvedValue(undefined);
const mockClearError = vi.fn();
const mockStop = vi.fn();

function makeReturn(overrides: Partial<UseSkillAgentReturn>): UseSkillAgentReturn {
  return {
    sessionId: "test-thread",
    messages: noMessages,
    toolCalls: [],
    thinkingContent: "",
    isThinking: false,
    stageLabel: null,
    delegations: [],
    fallbacks: [],
    compactions: [],
    tidyingUp: false,
    resolvedModel: null,
    sendMessage: mockSendMessage,
    isLoading: false,
    error: null,
    clearError: mockClearError,
    stop: mockStop,
    ...overrides,
  };
}

vi.mock("@/hooks/useSkillAgent", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/hooks/useSkillAgent")>();
  return { ...mod, useSkillAgent: vi.fn() };
});

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { uid: "test" }, loading: false }),
}));

vi.mock("@/providers/AGUIProvider", () => ({
  AGUIProvider: ({ children }: { children: React.ReactNode }) => children,
  useAGUIAgent: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => ({ get: vi.fn().mockReturnValue(null) }),
}));

vi.mock("@/hooks/useSlugResolution", () => ({
  useSlugResolution: () => ({ skillId: "test-skill-id", loading: false, notFound: false, error: null }),
}));

// 2026-06-11 cold-start UX (63e19ce): the chat input renders with
// placeholder "Connecting…" + disabled=true until BOTH `useBackendReady`
// reports ready=true AND `useSkillMeta` reports loading=false. The tests
// below assert against the steady-state placeholder ("Message…") and the
// input's disabled flag for error/non-error cases, so short-circuit both
// hooks. Without these mocks the page sits in "connecting" forever and
// the placeholder regex /message/i never matches.
vi.mock("@/hooks/useBackendReady", () => ({
  useBackendReady: () => ({ ready: true, lastError: null }),
}));

vi.mock("@/hooks/useSkillMeta", () => ({
  useSkillMeta: () => ({
    displayName: "Test Skill",
    ownerId: "test-owner",
    slug: "test-slug",
    mcpServerIds: [],
    initialMessage: "",
    welcome: null,
    model: "",
    voice: null,
    a2ui: { allowActionTriggeredRuns: false },
    loading: false,
  }),
}));

import { useSkillAgent } from "@/hooks/useSkillAgent";
import ChatPage from "@/app/chat/[...path]/page";

const paramsPromise = Promise.resolve({ path: ["@user-1", "test-slug"] });

const retryableError: StreamError = {
  kind: "http",
  status: 500,
  message: "Something went wrong on our end. Try again.",
  retryable: true,
  rawMessage: "HTTP 500",
};

const nonRetryableError: StreamError = {
  kind: "http",
  status: 401,
  message: "Session expired — please refresh the page",
  retryable: false,
  rawMessage: "HTTP 401",
};

beforeEach(() => {
  // JSDOM does not implement scrollTo — stub it so the scroll useEffect doesn't throw.
  Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo;
  vi.clearAllMocks();
});

describe("ChatShell — error display", () => {
  it("renders nothing error-related when error is null", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ error: null }));
    render(<ChatPage params={paramsPromise} />);
    // Error message text should not appear
    expect(screen.queryByRole("button", { name: /review and continue/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /dismiss/i })).toBeNull();
  });

  it("renders error message and both buttons for a retryable error", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ error: retryableError }));
    render(<ChatPage params={paramsPromise} />);
    expect(await screen.findByText(retryableError.message)).toBeTruthy();
    expect(screen.getByRole("button", { name: /review and continue/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /dismiss/i })).toBeTruthy();
  });

  it("renders error message with only Dismiss for a non-retryable error", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ error: nonRetryableError }));
    render(<ChatPage params={paramsPromise} />);
    expect(await screen.findByText(nonRetryableError.message)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /review and continue/i })).toBeNull();
    expect(screen.getByRole("button", { name: /dismiss/i })).toBeTruthy();
  });

  it("Dismiss calls clearError without sendMessage", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ error: retryableError }));
    render(<ChatPage params={paramsPromise} />);
    fireEvent.click(await screen.findByRole("button", { name: /dismiss/i }));
    expect(mockClearError).toHaveBeenCalledOnce();
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it("Review and continue clears the error without replaying an unknown action", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ error: retryableError }));
    render(<ChatPage params={paramsPromise} />);

    // Simulate a user having sent a message before the error (via the input)
    const input = screen.getByPlaceholderText(/message/i);
    // Input is disabled when error is set — change the mock to allow the input to be typed
    // We test the retry logic directly: the lastUserMessage ref is populated when handleSend runs.
    // Since error is already set on mount, we can't type in the input.
    // Verify recovery clears the error without replaying an uncertain action.
    fireEvent.click(await screen.findByRole("button", { name: /review and continue/i }));
    expect(mockClearError).toHaveBeenCalled();
    expect(mockSendMessage).not.toHaveBeenCalled();
    // sendMessage is called only when lastUserMessage is non-empty; it's empty here since
    // the error was set before any message was typed in this render.
    // The important assertion is clearError was called (not dismissed silently).
    expect(input).toBeTruthy(); // input exists in DOM
  });

  it("input is disabled when error is non-null", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ error: retryableError }));
    render(<ChatPage params={paramsPromise} />);
    const input = await screen.findByPlaceholderText(/message/i);
    expect(input).toHaveProperty("disabled", true);
  });

  it("input is enabled when error is null and not loading", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ error: null, isLoading: false }));
    render(<ChatPage params={paramsPromise} />);
    const input = await screen.findByPlaceholderText(/message/i);
    expect(input).toHaveProperty("disabled", false);
  });
});

describe("ChatShell — consistent conversation layout", () => {
  it("renders the empty conversation above the footer composer on a fresh session", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ messages: [] }));
    render(<ChatPage params={paramsPromise} />);
    const input = await screen.findByPlaceholderText(/message/i);
    expect(input.closest("footer")).toHaveClass("chat-composer");
    expect(screen.getByRole("heading", { name: "What would you like to talk about?" })).toBeInTheDocument();
    expect(screen.getByText(/ask a question, explore an idea/i)).toBeInTheDocument();
  });

  it("renders messages in the same conversation layout", async () => {
    vi.mocked(useSkillAgent).mockReturnValue(
      makeReturn({ messages: [{ id: "m1", role: "user", content: "hello there" }] }),
    );
    render(<ChatPage params={paramsPromise} />);
    expect(await screen.findByText("hello there")).toBeTruthy();
  });
});

vi.mock("@/hooks/useSessionAttachments", () => ({
  useSessionAttachments: () => ({ tabs: [], setTabs: vi.fn(), ready: true, saving: false, error: null, retrySave: vi.fn() }),
}));
