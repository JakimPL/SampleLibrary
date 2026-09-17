import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SHELL_FAILURE = "the shell read a layout that was not there";

const { failing } = vi.hoisted(() => ({ failing: { now: false } }));

vi.mock("../../src/workspace/WorkspaceShell", () => ({
    WorkspaceShell: () => {
        if (failing.now) {
            throw new Error(SHELL_FAILURE);
        }
        return <p>workspace</p>;
    },
}));

const { routes } = await import("../../src/navigation/router");

beforeEach(() => {
    failing.now = false;
});

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

    describe("when a view throws while it renders", () => {
        beforeEach(() => {
            // React reports a caught error to the console itself, which the suite reads as noise.
            vi.spyOn(console, "error").mockImplementation(() => undefined);
            failing.now = true;
        });

        afterEach(() => {
            vi.restoreAllMocks();
        });

        it("shows what broke and the way back to the workspace", () => {
            render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/"] })} />);

            expect(screen.getByRole("heading", { name: "This view stopped short" })).toBeInTheDocument();
            expect(screen.getByRole("alert")).toHaveTextContent(SHELL_FAILURE);
            expect(screen.getByRole("link", { name: "Back to the workspace" })).toHaveAttribute("href", "/");
        });
    });
});
