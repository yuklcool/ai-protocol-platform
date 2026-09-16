import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccessControlEditor } from "../AccessControlEditor";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AccessControlEditor", () => {
  it("keeps the public transition behind an explicit confirmation", () => {
    const onChange = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AccessControlEditor value={{ type: "private" }} onChange={onChange} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "public" } });

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(confirm.mock.calls[0]?.[0]).toMatch(/unauthenticated/i);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("writes the same access-control contract after confirmation", () => {
    const onChange = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AccessControlEditor value={{ type: "private" }} onChange={onChange} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "public" } });

    expect(onChange).toHaveBeenCalledWith({ type: "public" });
  });

  it("preserves the existing English labels outside an I18nProvider", () => {
    render(<AccessControlEditor value={{ type: "specific" }} onChange={() => {}} />);
    expect(screen.getByText("Who can use this skill")).toBeInTheDocument();
    expect(screen.getByText(/Allowed emails/)).toBeInTheDocument();
  });
});
