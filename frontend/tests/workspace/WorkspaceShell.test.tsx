import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../src/api/modules";
import { useSelectionStore } from "../../src/workspace/selectionStore";
import { WorkspaceShell } from "../../src/workspace/WorkspaceShell";

const { getModule } = vi.hoisted(() => ({ getModule: vi.fn() }));

vi.mock("../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../src/api/modules");
    return { ...actual, getModule };
});

function renderShellAt(initialPath: string): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={[initialPath]}>
            <Routes>
                <Route path="/" element={<WorkspaceShell />} />
                <Route path="/modules/:moduleHash" element={<WorkspaceShell />} />
                <Route path="/samples/:sampleHash" element={<WorkspaceShell />} />
            </Routes>
        </MemoryRouter>,
    );
}

/**
 * Every panel's own tab title, read from dockview's tab markup specifically -- a plain text query
 * would also match unrelated same-named controls a panel renders inside its own body, such as the
 * Cloud panel's Samples/Modules tab buttons.
 */
function panelTabTitles(): string[] {
    return Array.from(document.querySelectorAll(".dv-default-tab-content")).map((element) => element.textContent);
}

describe("WorkspaceShell", () => {
    it("mounts every default panel", () => {
        renderShellAt("/");

        const titles = panelTabTitles();
        for (const title of ["Modules", "Samples", "Cloud", "Waveform", "Module Detail", "Sample Detail", "Stats"]) {
            expect(titles).toContain(title);
        }
    });

    it("seeds the focused module from a deep-linked route without requiring a click", async () => {
        getModule.mockResolvedValue({
            hash: "abc",
            id: 1,
            title: "A Song",
            filename: "song.xm",
            tracker: "xm",
            channel_count: 4,
            pattern_count: 2,
            instrument_count: 1,
            sample_count: 0,
            file_size: 4096,
            ingested_at: "2026-01-01T00:00:00Z",
            occurrences: [],
        });

        renderShellAt("/modules/abc");

        await waitFor(() => {
            expect(useSelectionStore.getState().focusedModuleHash).toBe("abc");
        });
    });

    it("lets a closed panel be reopened through the Add panel menu", async () => {
        renderShellAt("/");
        expect(panelTabTitles()).toContain("Stats");

        fireEvent.click(screen.getByRole("button", { name: "Close Stats" }));
        expect(panelTabTitles()).not.toContain("Stats");

        fireEvent.click(await screen.findByRole("button", { name: "Stats" }));

        await waitFor(() => {
            expect(panelTabTitles()).toContain("Stats");
        });
    });
});
