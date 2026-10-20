import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InlineCitation } from "../InlineCitation";

describe("InlineCitation", () => {
  it("renders as a chip button for aitana:// URIs", () => {
    const navigate = vi.fn();
    render(
      <InlineCitation href="aitana://doc/doc-1/block/blk-1" navigateToBlock={navigate}>
        Q1 Summary
      </InlineCitation>,
    );
    expect(screen.getByRole("button", { name: /q1 summary/i })).toBeInTheDocument();
  });

  it("calls navigateToBlock with correct docId and blockId on click", () => {
    const navigate = vi.fn();
    render(
      <InlineCitation href="aitana://doc/doc-abc/block/blk-xyz" navigateToBlock={navigate}>
        Source
      </InlineCitation>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(navigate).toHaveBeenCalledWith("doc-abc", "blk-xyz");
  });

  it("renders a plain anchor for non-aitana GCS URLs", () => {
    const navigate = vi.fn();
    render(
      <InlineCitation
        href="https://storage.googleapis.com/bucket/file.pdf"
        navigateToBlock={navigate}
      >
        GCS doc
      </InlineCitation>,
    );
    const link = screen.getByRole("link", { name: /gcs doc/i });
    expect(link).toHaveAttribute("href", "https://storage.googleapis.com/bucket/file.pdf");
  });

  it("renders a plain anchor with href='#' for unknown URL schemes", () => {
    const navigate = vi.fn();
    render(
      <InlineCitation href="javascript:alert(1)" navigateToBlock={navigate}>
        Unsafe
      </InlineCitation>,
    );
    const link = screen.getByRole("link", { name: /unsafe/i });
    expect(link).toHaveAttribute("href", "#");
  });
});
