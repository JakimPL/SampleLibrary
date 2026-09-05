import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../../src/api/modules";
import { ModuleDetailPanel } from "../../../src/workspace/panels/ModuleDetailPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { getModule } = vi.hoisted(() => ({ getModule: vi.fn() }));

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, getModule };
});

function renderPanel(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<ModuleDetailPanel />} />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

const MODULE_DETAIL = {
    hash: "abc",
    id: 1,
    title: "A Song",
    filename: "song.xm",
    tracker: "xm",
    channel_count: 4,
    pattern_count: 2,
    instrument_count: 1,
    sample_count: 1,
    file_size: 4096,
    ingested_at: "2026-01-01T00:00:00Z",
    occurrences: [
        {
            properties: {
                sample_hash: "sample-1",
                occurrence: { module_hash: "abc", instrument_index: 0, sample_slot: 0 },
                name: "lead",
                rate: 8363,
                volume: 64,
                tracker: "xm",
                tuning: { relative_note: 0, finetune: 0 },
            },
            sample: { hash: "sample-1", depth: 16, channels: 1, frames: 4096, size_bytes: 8192, thumbnail: null },
        },
    ],
};

describe("ModuleDetailPanel", () => {
    it("shows a placeholder when no module is focused", () => {
        renderPanel();

        expect(screen.getByText(/No module focused yet/)).toBeInTheDocument();
    });

    it("shows the focused module's detail once loaded", async () => {
        getModule.mockResolvedValue(MODULE_DETAIL);
        useSelectionStore.getState().focusModule("abc");

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("heading", { name: "A Song" })).toBeInTheDocument();
        });
        expect(screen.getByRole("link", { name: "lead" })).toHaveAttribute("href", "/samples/sample-1");
    });

    it("shows an error notice when the module cannot be found", async () => {
        getModule.mockRejectedValue(new Error("no module catalogued with hash 'abc'"));
        useSelectionStore.getState().focusModule("abc");

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("no module catalogued with hash 'abc'");
        });
    });

    it("highlights a sample row on a plain click and navigates to it on a double-click", async () => {
        getModule.mockResolvedValue(MODULE_DETAIL);
        useSelectionStore.getState().focusModule("abc");
        renderPanel();
        const row = await waitFor(() => screen.getByRole("row", { name: /lead/ }));

        fireEvent.click(row);
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "sample-1" });

        fireEvent.doubleClick(row);
        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });
});
