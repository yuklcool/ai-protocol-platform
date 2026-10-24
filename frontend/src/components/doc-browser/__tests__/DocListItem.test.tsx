import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ParsedDocument } from "@/hooks/useDocBrowser";
import { DocListItem } from "../DocListItem";

// Focusing a file action opens its preview; document fetching has separate tests.
vi.mock("@/hooks/useDocument", () => ({
  useDocument: () => ({ doc: null, isLoading: false, error: null }),
}));

function makeDoc(overrides: Partial<ParsedDocument> = {}): ParsedDocument {
  return {
    id: "doc1",
    originalFilename: "report.docx",
    sourceFormat: "docx",
    parseStatus: "parsed",
    parseError: null,
    folderId: "folder1",
    userId: "user1",
    blockCount: 12,
    hasA2ui: true,
    ...overrides,
  };
}

describe("DocListItem", () => {
  it("renders filename and format badge", () => {
    render(<DocListItem doc={makeDoc()} onClick={vi.fn()} />);
    expect(screen.getByText("report.docx")).toBeInTheDocument();
    expect(screen.getByText("docx")).toBeInTheDocument();
  });

  it("shows green dot for parsed status", () => {
    render(<DocListItem doc={makeDoc({ parseStatus: "parsed" })} onClick={vi.fn()} />);
    const dot = screen.getByLabelText("可分析");
    expect(dot.className).toContain("bg-emerald-500");
  });

  it("shows amber pulsing dot for pending status", () => {
    render(<DocListItem doc={makeDoc({ parseStatus: "pending" })} onClick={vi.fn()} />);
    const dot = screen.getByLabelText("解析中");
    expect(dot.className).toContain("bg-amber-400");
    expect(dot.className).toContain("animate-pulse");
  });

  it("shows red dot for failed status", () => {
    render(<DocListItem doc={makeDoc({ parseStatus: "failed", parseError: null })} onClick={vi.fn()} />);
    const dot = screen.getByLabelText("处理失败");
    expect(dot.className).toContain("bg-destructive");
  });

  it("shows error message text when parse failed with error", () => {
    render(<DocListItem doc={makeDoc({ parseStatus: "failed", parseError: "API error: 500" })} onClick={vi.fn()} />);
    expect(screen.getByText("API error: 500")).toBeInTheDocument();
  });

  it("shows fallback error text when parse failed with no error message", () => {
    render(<DocListItem doc={makeDoc({ parseStatus: "failed", parseError: null })} onClick={vi.fn()} />);
    expect(screen.getByText("解析失败，内容不可用")).toBeInTheDocument();
  });

  it("does not show retry banner for parsed doc with blocks but no a2uiComponents", () => {
    // Regression: a2uiComponents is an optional render layer written by a
    // separate pipeline. Parsed docs with blockCount > 0 have content even
    // when hasA2ui is false — they should not show the retry banner.
    render(<DocListItem doc={makeDoc({ parseStatus: "parsed", blockCount: 12, hasA2ui: false })} onClick={vi.fn()} />);
    expect(screen.queryByText("没有可读内容，请重新解析")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重试解析" })).not.toBeInTheDocument();
  });

  it("shows retry banner for parsed doc with no blocks", () => {
    render(<DocListItem doc={makeDoc({ parseStatus: "parsed", blockCount: 0, hasA2ui: false })} onClick={vi.fn()} />);
    expect(screen.getByText("没有可读内容，请重新解析")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试解析" })).toBeInTheDocument();
  });

  it("calls onClick with the doc when clicked", async () => {
    const onClick = vi.fn();
    const doc = makeDoc();
    render(<DocListItem doc={doc} onClick={onClick} />);
    // Row is role=button; the inner delete/reparse <button>s share that role.
    // Click the row by walking up from the filename text.
    const row = screen.getByText("report.docx").closest("[role=\"button\"]");
    expect(row).not.toBeNull();
    await userEvent.click(row!);
    expect(onClick).toHaveBeenCalledWith(doc);
  });

  it("键盘触发删除确认时不会同时打开文件", async () => {
    const onClick = vi.fn();
    render(<DocListItem doc={makeDoc()} onClick={onClick} />);
    screen.getByRole("button", { name: "删除文件" }).focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "再次点击确认删除" })).toBeInTheDocument();
    expect(onClick).not.toHaveBeenCalled();
  });
});
