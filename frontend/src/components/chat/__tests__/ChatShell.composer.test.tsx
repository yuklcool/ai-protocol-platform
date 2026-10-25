// ChatShell — the composer wraps long text (2026-08-06 ONE UAT regression).
//
// The composer was a single-line `<input>`. An `<input>` CANNOT wrap: a long
// prompt scrolls sideways and the user cannot see what they typed. Two users
// reported it independently as their top complaint ("it never breaks the line,
// it keeps on writing horizontally" / "impossible to see the whole prompt"),
// on desktop web, not just mobile.
//
// The fix is a `<textarea>`, which wraps natively. That trade brings its own
// hazard: a textarea treats Enter as "newline", so without an explicit keydown
// handler the send key silently stops working — swapping a visible bug for a
// worse invisible one. Both halves are pinned here.
//
// SCOPE / HONESTY: jsdom does no layout, so this cannot prove pixels wrap. What
// it DOES prove is the property that makes wrapping possible (the control is a
// textarea, not an input, and isn't forced to one line) plus the full
// Enter/Shift+Enter contract. Visual confirmation is a browser job.

import { render, screen, act, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { UseSkillAgentReturn } from "@/hooks/useSkillAgent";

function makeReturn(overrides: Partial<UseSkillAgentReturn> = {}): UseSkillAgentReturn {
  return {
    sessionId: "test-thread",
    messages: [],
    toolCalls: [],
    thinkingContent: "",
    isThinking: false,
    stageLabel: null,
    delegations: [],
    fallbacks: [],
    compactions: [],
    tidyingUp: false,
    resolvedModel: null,
    sendMessage: vi.fn().mockResolvedValue(undefined),
    isLoading: false,
    error: null,
    clearError: vi.fn(),
    stop: vi.fn(),
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

type CustomEventHandler = (e: { event: { name?: unknown; value?: unknown } }) => void;
const subscribers: CustomEventHandler[] = [];

vi.mock("@/providers/AGUIProvider", () => ({
  useOptionalAGUIAgent: () => null,
  AGUIProvider: ({ children }: { children: React.ReactNode }) => children,
  useAGUIAgent: () => ({
    subscribe: ({ onCustomEvent }: { onCustomEvent?: CustomEventHandler }) => {
      if (onCustomEvent) subscribers.push(onCustomEvent);
      return { unsubscribe: () => {} };
    },
  }),
}));

const navigation = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => navigation.params,
}));

vi.mock("@/hooks/useDocBrowser", () => ({
  useDocBrowser: () => ({ folders: [], documents: [], filteredDocuments: [], activeFolderId: null, searchQuery: "", setActiveFolderId: vi.fn(), setSearchQuery: vi.fn(), error: null, isLoading: false }),
}));
vi.mock("@/components/document/DocumentPanel", () => ({ DocumentPanel: () => null }));
vi.mock("@/hooks/useDocumentSessions", () => ({ useDocumentSessions: () => ({ sessions: [], isLoading: false, error: null }) }));
vi.mock("@/hooks/useSessionAttachments", () => ({ useSessionAttachments: vi.fn() }));
vi.mock("@/hooks/useSessionMessages", () => ({
  useSessionMessages: vi.fn(),
}));
vi.mock("@/hooks/useSessionActivity", () => ({
  useSessionActivity: () => ({ toolCalls: [], delegations: [], sessionStartTs: null }),
}));
vi.mock("@/lib/importByReference", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/importByReference")>(),
  importByReference: vi.fn(),
}));

vi.mock("@/hooks/useSlugResolution", () => ({
  useSlugResolution: () => ({ skillId: "test-skill-id", loading: false, notFound: false, error: null }),
}));

vi.mock("@/hooks/useBackendReady", () => ({
  useBackendReady: () => ({ ready: true, lastError: null }),
}));

vi.mock("@/hooks/useSkillMeta", () => ({
  useSkillMeta: vi.fn(() => ({
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
  })),
}));

vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));
vi.mock("@/lib/documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/documents")>();
  return {
    ...actual,
    documentRequest: (path: string, init?: RequestInit) => path === "/documents/capabilities"
      ? Promise.resolve({ formats: [{ extension: "pdf", description: "PDF" }], maxFileBytes: 25 * 1024 * 1024, maxDocuments: 10, limitations: "" })
      : actual.documentRequest(path, init),
  };
});

import { fetchWithAuth } from "@/lib/apiClient";
import { stashPendingSkillSwitch, readPendingSkillSwitch, clearPendingSkillSwitch } from "@/lib/skillSwitch";
import { useSessionAttachments } from "@/hooks/useSessionAttachments";
import { useSessionMessages } from "@/hooks/useSessionMessages";
import { importByReference } from "@/lib/importByReference";
import { ChatShell } from "../ChatShell";
import type { User } from "@/lib/firebase";
import { useSkillAgent } from "@/hooks/useSkillAgent";

async function renderChat() {
  await act(async () => {
    render(shell());
  });
  await waitFor(() => expect(subscribers.length).toBeGreaterThan(0));
}

/** The composer control, found the way a user finds it — by its placeholder. */
function composer(): HTMLTextAreaElement {
  return screen.getByPlaceholderText("Message…") as HTMLTextAreaElement;
}

/** A prompt long enough that it could only ever be read if it wraps — the
 * shape of the real ONE prompts that triggered the report. */
const LONG_PROMPT =
  "Compare the termination clauses in these two PPA contracts and tell me " +
  "which one is more favourable to the offtaker, with reference to the " +
  "change-in-law provisions and the settlement timeline.";

beforeEach(() => {
  Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo;
  subscribers.length = 0;
  vi.clearAllMocks();
  vi.mocked(importByReference).mockReset();
  vi.mocked(fetchWithAuth).mockReset();
  clearPendingSkillSwitch();
  window.sessionStorage.clear();
  navigation.params = new URLSearchParams();
  vi.mocked(useSessionMessages).mockReturnValue({ initialMessages: [], a2uiSurfaces: [], isLoadingHistory: false, historyError: null, sessionGone: false, transcriptUnavailable: false });
  vi.mocked(useSessionAttachments).mockReturnValue({ tabs: [], setTabs: vi.fn(), ready: true, saving: false, error: null, retrySave: vi.fn() });
  vi.mocked(useSkillAgent).mockReturnValue(makeReturn());
});

describe("ChatShell composer — wrapping (2026-08-06 ONE UAT)", () => {
  it("keeps the same composer mounted when an empty chat receives its first message", async () => {
    const view = render(shell());
    const input = composer();
    input.focus();
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ messages: [{ id: "first", role: "user", content: "First message" }] }));
    view.rerender(shell());
    expect(composer()).toBe(input);
    expect(input).toHaveFocus();
    expect(screen.getByText("First message")).toBeInTheDocument();
    expect(screen.queryByText("What would you like to talk about?")).not.toBeInTheDocument();
  });

  it("shows a resumed conversation's loading state and saved answer", async () => {
    navigation.params = new URLSearchParams("session=saved");
    const history = { initialMessages: [], a2uiSurfaces: [], isLoadingHistory: true, historyError: null, sessionGone: false, transcriptUnavailable: false };
    vi.mocked(useSessionMessages).mockReturnValue(history);
    const view = render(shell());
    expect(screen.getByRole("status")).toHaveTextContent("Loading conversation messages");
    vi.mocked(useSessionMessages).mockReturnValue({ ...history, isLoadingHistory: false, initialMessages: [{ id: "saved-answer", role: "assistant", content: "Saved answer" }] });
    view.rerender(shell());
    expect(screen.getByText("Saved answer")).toBeInTheDocument();
    expect(screen.queryByText("What would you like to talk about?")).not.toBeInTheDocument();
  });

  it("is a textarea, not a single-line input", async () => {
    await renderChat();
    const el = composer();

    // The regression itself. An <input> cannot wrap at any CSS setting, so
    // this tag check IS the fix — not a proxy for it.
    expect(el.tagName).toBe("TEXTAREA");
  });

  it("does not suppress wrapping via rows/wrap attributes", async () => {
    await renderChat();
    const el = composer();

    // A textarea can still be forced to one line: wrap="off" reintroduces
    // exactly the horizontal-scroll bug we just fixed.
    expect(el.getAttribute("wrap")).not.toBe("off");
    // Resting height is one row (auto-grow handles the rest) — a taller
    // default would eat chat space for the common short message.
    expect(el.rows).toBe(1);
  });

  it("holds a long multi-line value without truncating it", async () => {
    await renderChat();
    const el = composer();

    fireEvent.change(el, { target: { value: LONG_PROMPT } });
    expect(el.value).toBe(LONG_PROMPT);

    // Explicit newlines survive too — an <input> would have dropped them.
    fireEvent.change(el, { target: { value: "line one\nline two" } });
    expect(el.value).toBe("line one\nline two");
  });

  it("sends on Enter", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    await renderChat();
    const el = composer();

    fireEvent.change(el, { target: { value: LONG_PROMPT } });
    fireEvent.keyDown(el, { key: "Enter" });

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    expect(sendMessage.mock.calls[0][0]).toBe(LONG_PROMPT);
  });

  it("inserts a newline on Shift+Enter instead of sending", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    await renderChat();
    const el = composer();

    fireEvent.change(el, { target: { value: "first line" } });
    fireEvent.keyDown(el, { key: "Enter", shiftKey: true });

    expect(sendMessage).not.toHaveBeenCalled();
    // Not preventDefault'd, so the browser's own newline insertion still runs.
    expect(el.value).toBe("first line");
  });

  it("does not send on Enter while an IME composition is open", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    await renderChat();
    const el = composer();

    fireEvent.change(el, { target: { value: "spanish text" } });
    // Enter commits the candidate for CJK/accented input; treating it as
    // "send" would fire a half-typed message. ONE's users type Spanish.
    fireEvent.keyDown(el, { key: "Enter", isComposing: true });

    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("still refuses to send an empty or whitespace-only draft on Enter", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    await renderChat();
    const el = composer();

    fireEvent.keyDown(el, { key: "Enter" });
    fireEvent.change(el, { target: { value: "   \n  " } });
    fireEvent.keyDown(el, { key: "Enter" });

    expect(sendMessage).not.toHaveBeenCalled();
  });
});

function shell() {
  return <ChatShell skillId="current-skill" pathPrefix="/chat/@current/current-slug" user={{ uid: "test" } as User} />;
}

function attachmentState() {
  return vi.mocked(useSessionAttachments).mock.results[0].value as ReturnType<typeof useSessionAttachments>;
}

// 所有回归均渲染真实 ChatShell，直接操作输入框、历史按钮和导入错误提示。
describe("ChatShell — 历史和附件恢复", () => {
  it("桌面主动展开的侧栏不会在首条消息出现后自行关闭", async () => {
    const view = render(shell());
    await userEvent.click(screen.getByRole("button", { name: "Open conversation files" }));
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ messages: [{ id: "first", role: "user", content: "Keep the sidebar open" }] }));
    view.rerender(shell());
    expect(screen.getByRole("complementary", { name: "Conversation resources" })).toBeVisible();
    expect(window.sessionStorage.getItem("aitana.sidebar.open")).toBe("1");
  });

  it.each([
    { ready: false, saving: false, error: null },
    { ready: false, saving: false, error: "Attachment initialization failed" },
    { ready: true, saving: true, error: null },
    { ready: true, saving: false, error: "Attachment save failed" },
  ])("附件阻断时仍可编辑，但按钮、Enter 和表单提交都不能发送：%j", async (state) => {
    const sendMessage = vi.fn();
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    vi.mocked(useSessionAttachments).mockReturnValue({ tabs: [], setTabs: vi.fn(), retrySave: vi.fn(), ...state });
    render(shell());
    const input = composer();
    expect(input).toBeEnabled();
    await userEvent.type(input, "保留草稿");
    expect(input).toHaveValue("保留草稿");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.submit(screen.getByRole("form", { name: "Message…" }));
    expect(sendMessage).not.toHaveBeenCalled();
    expect(input).toHaveValue("保留草稿");
  });

  it("附件恢复后发送原草稿，不做纯文字降级", async () => {
    const sendMessage = vi.fn();
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    vi.mocked(useSessionAttachments).mockReturnValue({ tabs: [], setTabs: vi.fn(), retrySave: vi.fn(), ready: false, saving: false, error: "Failed" });
    const view = render(shell());
    await userEvent.type(composer(), "draft survives");
    vi.mocked(useSessionAttachments).mockReturnValue({ ...attachmentState(), ready: true, error: null });
    view.rerender(shell());
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sendMessage).toHaveBeenCalledWith("draft survives", { documentIds: [] });
  });

  it("未解析的已选附件不能通过 Enter 绕过发送阻断", async () => {
    const sendMessage = vi.fn();
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    const view = render(shell());
    vi.mocked(useSessionAttachments).mockReturnValue({ ...attachmentState(), tabs: [{ id: "doc", filename: "pending.pdf", format: "pdf", included: true, parseStatus: "pending" }] });
    view.rerender(shell());
    fireEvent.change(composer(), { target: { value: "analyze" } });
    expect(composer()).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    fireEvent.keyDown(composer(), { key: "Enter" });
    expect(sendMessage).not.toHaveBeenCalled();
    await act(async () => {});
  });

  it.each(["pending", "failed", "pending_ai_extraction"] as const)("已选 %s 附件不能绕过流式错误重试", async (parseStatus) => {
    const sendMessage = vi.fn();
    const clearError = vi.fn();
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage, clearError }));
    const view = render(shell());
    fireEvent.change(composer(), { target: { value: "analyze again" } });
    fireEvent.keyDown(composer(), { key: "Enter" });
    expect(sendMessage).toHaveBeenCalledTimes(1);
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage, clearError, error: { kind: "network", message: "Connection failed", rawMessage: "Connection failed", retryable: true } }));
    vi.mocked(useSessionAttachments).mockReturnValue({ ...attachmentState(), tabs: [{ id: "doc", filename: "unreadable.pdf", format: "pdf", included: true, parseStatus }] });
    view.rerender(shell());
    await userEvent.click(screen.getByRole("button", { name: "Review and continue" }));
    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(clearError).not.toHaveBeenCalled();
    vi.mocked(useSessionAttachments).mockReturnValue({ ...attachmentState(), tabs: [{ id: "doc", filename: "unreadable.pdf", format: "pdf", included: true, parseStatus: "parsed" }] });
    view.rerender(shell());
    await userEvent.click(screen.getByRole("button", { name: "Review and continue" }));
    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(clearError).toHaveBeenCalledTimes(1);
    expect(composer()).toHaveValue("analyze again");
  });

  it("附件尚不可读时保留技能切换请求，恢复后才发送且仅一次", async () => {
    const sendMessage = vi.fn();
    stashPendingSkillSwitch({ targetSkillId: "current-skill", threadId: "test-thread", prompt: "continue analysis", documentIds: ["doc"] });
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ sendMessage }));
    vi.mocked(useSessionAttachments).mockReturnValue({ tabs: [{ id: "doc", filename: "pending.pdf", format: "pdf", included: true, parseStatus: "pending" }], ready: false, saving: false, error: null, setTabs: vi.fn(), retrySave: vi.fn() });
    const view = render(shell());
    expect(sendMessage).not.toHaveBeenCalled();
    expect(readPendingSkillSwitch()).not.toBeNull();
    vi.mocked(useSessionAttachments).mockReturnValue({ ...attachmentState(), tabs: [{ id: "doc", filename: "pending.pdf", format: "pdf", included: true, parseStatus: "parsed" }], ready: true });
    view.rerender(shell());
    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(sendMessage).toHaveBeenCalledWith("continue analysis", { documentIds: ["doc"] });
    expect(readPendingSkillSwitch()).toBeNull();
    view.rerender(shell());
    expect(sendMessage).toHaveBeenCalledTimes(1);
    await act(async () => {});
  });

  it("首次 URL pin 继续使用当前 path 并保留已有 query", async () => {
    navigation.params = new URLSearchParams("view=detail");
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ messages: [{ id: "first", role: "user", content: "hello" }] }));
    render(shell());
    expect(navigation.replace).toHaveBeenCalledWith("/chat/@current/current-slug?view=detail&session=test-thread");
    await act(async () => {});
  });

  it("运行时保留停止按钮和 Esc 语义，不发送新消息", async () => {
    const stop = vi.fn();
    const sendMessage = vi.fn();
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ isLoading: true, stop, sendMessage }));
    render(shell());
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(stop).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(stop).toHaveBeenCalledTimes(2);
    fireEvent.submit(screen.getByRole("form", { name: "Message…" }));
    expect(sendMessage).not.toHaveBeenCalled();
  });
});

const importedDoc = { id: "imported", originalFilename: "contract.pdf", sourceFormat: "pdf", parseStatus: "parsed" as const, parseError: null, folderId: "", userId: "", blockCount: 1, hasA2ui: false };
const importToolCalls: UseSkillAgentReturn["toolCalls"] = [{ id: "tc", name: "get_document_content", argsJson: JSON.stringify({ gs_url: "gs://library/contract.pdf" }), status: "success" }];

describe("ChatShell — 导入失败反馈", () => {
  it("手动重试通过真实导入 helper 再次发送 POST，而非复用失败结果", async () => {
    const actual = await vi.importActual<typeof import("@/lib/importByReference")>("@/lib/importByReference");
    vi.mocked(importByReference).mockImplementation(actual.importByReference);
    vi.mocked(fetchWithAuth)
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: "Storage unavailable" }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ docId: "imported", status: "parsed", originalFilename: "contract.pdf" }) } as Response);
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ toolCalls: importToolCalls }));
    render(shell());
    await screen.findByRole("alert");
    expect(fetchWithAuth).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Retry import" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(fetchWithAuth).toHaveBeenCalledTimes(2);
    expect(fetchWithAuth).toHaveBeenLastCalledWith("/api/proxy/api/documents/import-by-reference", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bucket: "library", object: "contract.pdf", skillId: "current-skill" }),
    });
    expect(attachmentState().setTabs).toHaveBeenCalledTimes(1);
  });

  it.each(["session", "skill", "unmount"] as const)("%s 变化后忽略旧导入的成功、错误及异常", async (change) => {
    for (const outcome of ["success", "error", "rejection"] as const) {
      let finish!: (result: Awaited<ReturnType<typeof importByReference>>) => void;
      let reject!: (error: Error) => void;
      vi.mocked(importByReference).mockReturnValueOnce(new Promise((resolve, fail) => { finish = resolve; reject = fail; }));
      vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ toolCalls: importToolCalls }));
      const setTabs = vi.fn();
      vi.mocked(useSessionAttachments).mockReturnValue({ tabs: [], setTabs, ready: true, saving: false, error: null, retrySave: vi.fn() });
      const view = render(shell());
      expect(screen.getByRole("status")).toHaveTextContent("Importing document…");
      vi.mocked(useSkillAgent).mockReturnValue(makeReturn());
      if (change === "unmount") view.unmount();
      else if (change === "session") {
        navigation.params = new URLSearchParams(`session=next-${outcome}`);
        view.rerender(shell());
      } else {
        view.rerender(<ChatShell skillId="next-skill" pathPrefix="/chat/next-skill" user={{ uid: "test" } as User} />);
      }
      await act(async () => {
        if (outcome === "rejection") reject(new Error("Old import failed"));
        else finish(outcome === "success" ? { doc: importedDoc } : { status: 503, message: "Old import failed" });
      });
      expect(setTabs).not.toHaveBeenCalled();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.queryByText("Importing document…")).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it("切换会话后可重新导入相同文件，旧请求完成不能解除新请求忙碌状态", async () => {
    let finishOld!: (result: Awaited<ReturnType<typeof importByReference>>) => void;
    let finishNew!: (result: Awaited<ReturnType<typeof importByReference>>) => void;
    vi.mocked(importByReference)
      .mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }))
      .mockReturnValueOnce(new Promise((resolve) => { finishNew = resolve; }));
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ toolCalls: importToolCalls }));
    const view = render(shell());
    navigation.params = new URLSearchParams("session=new-session");
    view.rerender(shell());
    expect(importByReference).toHaveBeenCalledTimes(2);
    await act(async () => finishOld({ doc: importedDoc }));
    expect(attachmentState().setTabs).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Importing document…");
    await act(async () => finishNew({ doc: importedDoc }));
    expect(attachmentState().setTabs).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Importing document…")).not.toBeInTheDocument();
  });

  it("首次 URL pin 不取消同一会话的在途导入", async () => {
    let finish!: (result: Awaited<ReturnType<typeof importByReference>>) => void;
    vi.mocked(importByReference).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ toolCalls: importToolCalls, messages: [{ id: "first", role: "user", content: "hello" }] }));
    const view = render(shell());
    expect(navigation.replace).toHaveBeenCalledWith("/chat/@current/current-slug?session=test-thread");
    navigation.params = new URLSearchParams("session=test-thread");
    view.rerender(shell());
    await act(async () => finish({ doc: importedDoc }));
    expect(attachmentState().setTabs).toHaveBeenCalledTimes(1);
    expect(importByReference).toHaveBeenCalledTimes(1);
  });

  it("并行导入另一文件成功不能抹去仍需重试的失败", async () => {
    let finish!: (result: Awaited<ReturnType<typeof importByReference>>) => void;
    vi.mocked(importByReference)
      .mockResolvedValueOnce({ status: 503, message: "First import failed" })
      .mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ toolCalls: [...importToolCalls, { ...importToolCalls[0], id: "tc2", argsJson: JSON.stringify({ gs_url: "gs://library/other.pdf" }) }] }));
    render(shell());
    expect(await screen.findByRole("alert")).toHaveTextContent("First import failed");
    await act(async () => finish({ doc: { ...importedDoc, id: "other", originalFilename: "other.pdf" } }));
    expect(screen.getByRole("alert")).toHaveTextContent("Could not import contract.pdf: First import failed");
    expect(screen.getByRole("button", { name: "Retry import" })).toBeEnabled();
  });

  it("自动导入失败在输入附近显示 alert，仅手动重试且请求中不能重复提交", async () => {
    vi.mocked(importByReference).mockResolvedValueOnce({ status: 503, message: "Storage unavailable" });
    vi.mocked(useSkillAgent).mockReturnValue(makeReturn({ toolCalls: [{ id: "tc", name: "get_document_content", argsJson: JSON.stringify({ gs_url: "gs://library/contract.pdf" }), status: "success" }] }));
    const view = render(shell());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not import contract.pdf: Storage unavailable");
    expect(alert.parentElement).toContainElement(composer());
    await userEvent.type(composer(), "keep editing");
    view.rerender(shell());
    expect(importByReference).toHaveBeenCalledTimes(1);
    let finish!: (result: Awaited<ReturnType<typeof importByReference>>) => void;
    vi.mocked(importByReference).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const retry = within(alert).getByRole("button", { name: "Retry import" });
    retry.focus();
    await userEvent.keyboard("{Enter}");
    expect(importByReference).toHaveBeenCalledTimes(2);
    expect(importByReference).toHaveBeenLastCalledWith("library", "contract.pdf", "current-skill");
    expect(retry).toBeDisabled();
    await userEvent.keyboard("{Enter}");
    expect(importByReference).toHaveBeenCalledTimes(2);
    await act(async () => finish({ doc: { id: "imported", originalFilename: "contract.pdf", sourceFormat: "pdf", parseStatus: "parsed", parseError: null, folderId: "", userId: "", blockCount: 1, hasA2ui: false } }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(attachmentState().setTabs).toHaveBeenCalledTimes(1);
    expect(composer()).toHaveValue("keep editing");
    view.rerender(shell());
    expect(importByReference).toHaveBeenCalledTimes(2);
  });
});
