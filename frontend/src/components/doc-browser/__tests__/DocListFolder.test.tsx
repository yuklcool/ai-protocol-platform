import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Folder, ParsedDocument } from "@/hooks/useDocBrowser";
import { DocListFolder } from "../DocListFolder";

const folder: Folder = {
  id: "f1",
  name: "Q1 Financial Review",
  userId: "user1",
  docCount: 3,
  parsedCount: 2,
};

const docs: ParsedDocument[] = [
  {
    id: "d1",
    originalFilename: "summary.docx",
    sourceFormat: "docx",
    parseStatus: "parsed", parseError: null,
    folderId: "f1",
    userId: "user1",
    blockCount: 10,
    hasA2ui: true,
  },
  {
    id: "d2",
    originalFilename: "budget.xlsx",
    sourceFormat: "xlsx",
    parseStatus: "pending", parseError: null,
    folderId: "f1",
    userId: "user1",
    blockCount: null,
    hasA2ui: false,
  },
];

describe("DocListFolder", () => {
  it("renders folder name and doc count badge", () => {
    render(
      <DocListFolder
        folder={folder}
        documents={docs}
        isActive={true}
        onSelect={vi.fn()}
        onDocClick={vi.fn()}
      />,
    );
    expect(screen.getByText("Q1 Financial Review")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows documents when active (open by default)", () => {
    render(
      <DocListFolder
        folder={folder}
        documents={docs}
        isActive={true}
        onSelect={vi.fn()}
        onDocClick={vi.fn()}
      />,
    );
    expect(screen.getByText("summary.docx")).toBeInTheDocument();
    expect(screen.getByText("budget.xlsx")).toBeInTheDocument();
  });

  it("toggles open/closed on click", async () => {
    const view = render(
      <DocListFolder
        folder={folder}
        documents={docs}
        isActive={false}
        onSelect={vi.fn()}
        onDocClick={vi.fn()}
      />,
    );
    // Initially closed (isActive=false)
    expect(screen.queryByText("summary.docx")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /q1 financial/i }));
    view.rerender(<DocListFolder folder={folder} documents={docs} isActive={true} onSelect={vi.fn()} onDocClick={vi.fn()} />);
    expect(screen.getByText("summary.docx")).toBeInTheDocument();
    view.rerender(<DocListFolder folder={folder} documents={[]} isActive={false} onSelect={vi.fn()} onDocClick={vi.fn()} />);
    expect(screen.queryByText("暂无文件")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /q1 financial/i })).toHaveAttribute("aria-expanded", "false");
  });

  it("calls onSelect when folder is opened", async () => {
    const onSelect = vi.fn();
    render(
      <DocListFolder
        folder={folder}
        documents={docs}
        isActive={false}
        onSelect={onSelect}
        onDocClick={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /q1 financial/i }));
    expect(onSelect).toHaveBeenCalledWith("f1");
  });

  it("折叠当前文件夹时通知父组件，读取期间不显示空状态", async () => {
    const onSelect = vi.fn();
    render(<DocListFolder folder={folder} documents={[]} isActive isLoading onSelect={onSelect} onDocClick={vi.fn()} />);
    expect(screen.queryByText("暂无文件")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /q1 financial/i }));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("calls onDocClick when a document is clicked", async () => {
    const onDocClick = vi.fn();
    render(
      <DocListFolder
        folder={folder}
        documents={docs}
        isActive={true}
        onSelect={vi.fn()}
        onDocClick={onDocClick}
      />,
    );
    await userEvent.click(screen.getByText("summary.docx"));
    expect(onDocClick).toHaveBeenCalledWith(docs[0]);
  });
});
