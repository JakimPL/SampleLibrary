import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../../src/api/modules";
import { ModulesListPanel } from "../../../src/workspace/panels/ModulesListPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { listModules } = vi.hoisted(() => ({ listModules: vi.fn() }));

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, listModules };
});

function renderPanel(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<ModulesListPanel />} />
                <Route path="/modules/:moduleHash" element={<p>module route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

const SAMPLE_MODULE = {
    hash: "abc",
    id: 1,
    title: "A Song",
    filename: "song.xm",
    tracker: "xm",
    channel_count: 4,
    pattern_count: 2,
    instrument_count: 1,
    sample_count: 3,
    file_size: 4096,
    ingested_at: "2026-01-01T00:00:00Z",
};

describe("ModulesListPanel", () => {
    it("shows a loading state before the modules arrive", () => {
        listModules.mockReturnValue(new Promise(() => undefined));

        renderPanel();

        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("renders the fetched modules once loaded", async () => {
        listModules.mockResolvedValue({ items: [SAMPLE_MODULE], total: 1, limit: 50, offset: 0 });

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("link", { name: "A Song" })).toHaveAttribute("href", "/modules/abc");
        });
        expect(screen.getByText("song.xm")).toBeInTheDocument();
        expect(screen.getByText("4.0 KiB")).toBeInTheDocument();
    });

    it("shows an error notice when the request fails", async () => {
        listModules.mockRejectedValue(new Error("network down"));

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("network down");
        });
    });

    it("highlights a module in the shared selection store on a plain click", async () => {
        listModules.mockResolvedValue({ items: [SAMPLE_MODULE], total: 1, limit: 50, offset: 0 });
        renderPanel();
        const row = await waitFor(() => screen.getByRole("row", { name: /A Song/ }));

        fireEvent.click(row);

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "module", hash: "abc" });
    });

    it("navigates to the module's own route on a double-click", async () => {
        listModules.mockResolvedValue({ items: [SAMPLE_MODULE], total: 1, limit: 50, offset: 0 });
        renderPanel();
        const row = await waitFor(() => screen.getByRole("row", { name: /A Song/ }));

        fireEvent.doubleClick(row);

        expect(await screen.findByText("module route")).toBeInTheDocument();
    });
});
