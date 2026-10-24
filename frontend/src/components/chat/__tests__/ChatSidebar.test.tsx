import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatSidebar } from "../ChatSidebar";

beforeEach(() => window.sessionStorage.clear());
afterEach(() => { window.sessionStorage.clear(); vi.restoreAllMocks(); });

function FileSearch() {
  const [query, setQuery] = useState("");
  return <input aria-label="File search" value={query} onChange={event => setQuery(event.target.value)} />;
}

describe("ChatSidebar", () => {
  it("用键盘切换完整列表，保留文件搜索，并记住当前页签", async () => {
    render(<ChatSidebar open onOpenChange={vi.fn()} files={<FileSearch />} history={<p>Recent work</p>} />);
    await userEvent.type(screen.getByRole("textbox", { name: "File search" }), "report");
    screen.getByRole("tab", { name: "Files" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Conversations" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Conversations" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Recent work")).toBeVisible();
    expect(window.sessionStorage.getItem("aitana.sidebar.tab")).toBe("history");
    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("textbox", { name: "File search" })).toHaveValue("report");
  });

  it("保留资料库和助手界面，失效的页签回到文件", async () => {
    window.sessionStorage.setItem("aitana.sidebar.tab", "library");
    const props = { open: true, onOpenChange: vi.fn(), files: <p>My files</p>, history: <p>Recent work</p> };
    const view = render(<ChatSidebar {...props} library={<p>Curated sources</p>} assistant={<p>Interactive surface</p>} />);
    expect(screen.getByText("Curated sources")).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Assistant" }));
    expect(screen.getByText("Interactive surface")).toBeVisible();
    view.rerender(<ChatSidebar {...props} />);
    expect(screen.getByRole("tab", { name: "Files" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("My files")).toBeVisible();
  });

  it("手机抽屉用 Esc 关闭并将焦点还给入口", async () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({ ...window.matchMedia(""), matches: true });
    function MobileSidebar() {
      const [open, setOpen] = useState(true);
      return <>
        <button id="chat-resource-toggle" onClick={() => setOpen(true)}>Open resources</button>
        <ChatSidebar open={open} onOpenChange={setOpen} files={<FileSearch />} history={<p>Recent work</p>} />
      </>;
    }
    render(<MobileSidebar />);
    expect(screen.getByRole("dialog", { name: "Conversation resources" })).toBeVisible();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open resources" })).toHaveFocus();
  });
});
