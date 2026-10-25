import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { TRANSPORT_FIELD } from "@/lib/branding";

const createClient = vi.hoisted(() => vi.fn());
vi.mock("@/lib/mcpClient", () => ({ createDevDirectMcpClient: createClient }));
vi.mock("@/components/protocols/MCPAppToolCallRouter", () => ({
  MCPAppToolCallRouter: () => <div data-testid="connected-router" />,
}));
import PassivePage from "../passive/page";

beforeEach(() => createClient.mockReset());

it("shows a connection failure, retries explicitly and closes both clients", async () => {
  const failed = { [TRANSPORT_FIELD]: {}, connect: vi.fn().mockRejectedValue(new Error("offline")), close: vi.fn().mockResolvedValue(undefined) };
  const connected = { [TRANSPORT_FIELD]: {}, connect: vi.fn().mockResolvedValue(undefined), close: vi.fn().mockResolvedValue(undefined) };
  createClient.mockReturnValueOnce(failed).mockReturnValueOnce(connected);
  const { unmount } = render(<PassivePage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not connect");
  expect(screen.queryByText("Connecting to map-server…")).not.toBeInTheDocument();
  expect(screen.queryByTestId("connected-router")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry connection" }));
  expect(await screen.findByTestId("connected-router")).toBeVisible();
  expect(failed.close).toHaveBeenCalledOnce();
  unmount();
  await waitFor(() => expect(connected.close).toHaveBeenCalledOnce());
});
