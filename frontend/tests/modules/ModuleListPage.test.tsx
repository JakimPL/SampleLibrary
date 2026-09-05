import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../src/api/modules";
import { ModuleListPage } from "../../src/modules/ModuleListPage";

const { listModules } = vi.hoisted(() => ({ listModules: vi.fn() }));

vi.mock("../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../src/api/modules");
    return { ...actual, listModules };
});

function renderPage(): ReturnType<typeof render> {
    return render(
        <MemoryRouter>
            <ModuleListPage />
        </MemoryRouter>,
    );
}

describe("ModuleListPage", () => {
    it("shows a loading state before the modules arrive", () => {
        listModules.mockReturnValue(new Promise(() => undefined));

        renderPage();

        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("renders the fetched modules once loaded", async () => {
        listModules.mockResolvedValue({
            items: [{ hash: "abc", id: 1, title: "A Song", filename: "song.xm", tracker: "xm", sample_count: 3 }],
            total: 1,
            limit: 50,
            offset: 0,
        });

        renderPage();

        await waitFor(() => {
            expect(screen.getByText("A Song")).toBeInTheDocument();
        });
        expect(screen.getByRole("link", { name: "A Song" })).toHaveAttribute("href", "/modules/abc");
    });

    it("links a module with an empty title through the [untitled] placeholder", async () => {
        listModules.mockResolvedValue({
            items: [{ hash: "abc", id: 1, title: "", filename: "song.xm", tracker: "xm", sample_count: 3 }],
            total: 1,
            limit: 50,
            offset: 0,
        });

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("link", { name: "[untitled]" })).toHaveAttribute("href", "/modules/abc");
        });
    });

    it("shows an error notice when the request fails", async () => {
        listModules.mockRejectedValue(new Error("network down"));

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("network down");
        });
    });
});
