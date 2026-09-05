import { render, screen, waitFor } from "@testing-library/react";
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

describe("WorkspaceShell", () => {
    it("mounts every default panel", () => {
        renderShellAt("/");

        expect(screen.getByText("Modules")).toBeInTheDocument();
        expect(screen.getByText("Samples")).toBeInTheDocument();
        expect(screen.getByText("Cloud")).toBeInTheDocument();
        expect(screen.getByText("Module Detail")).toBeInTheDocument();
        expect(screen.getByText("Sample Detail")).toBeInTheDocument();
        expect(screen.getByText("Stats")).toBeInTheDocument();
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
});
