import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/workspace/WorkspaceShell", () => ({
    WorkspaceShell: () => <p>workspace</p>,
}));

const { routes } = await import("../../src/navigation/router");

describe("routes", () => {
    it("shows a page saying nothing lives at an address the application does not answer", () => {
        render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/no/such/view"] })} />);

        expect(screen.getByRole("heading", { name: "Nothing lives at this address" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Back to the workspace" })).toHaveAttribute("href", "/");
    });

    it("keeps the workspace at a sample's own address", () => {
        render(
            <RouterProvider router={createMemoryRouter(routes, { initialEntries: [`/samples/${"a".repeat(64)}`] })} />,
        );

        expect(screen.getByText("workspace")).toBeInTheDocument();
    });
});
