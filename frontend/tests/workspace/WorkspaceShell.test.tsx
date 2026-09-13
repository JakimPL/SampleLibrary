import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../src/api/modules";
import type * as SamplesApi from "../../src/api/samples";
import { KNOWN_PANELS_STORAGE_KEY, LAYOUT_STORAGE_KEY } from "../../src/workspace/dockviewPersistence";
import { PANEL_REGISTRY } from "../../src/workspace/panelRegistry";
import { useSelectionStore } from "../../src/workspace/selectionStore";
import { WorkspaceShell } from "../../src/workspace/WorkspaceShell";

const { getModule } = vi.hoisted(() => ({ getModule: vi.fn() }));
const { getSample, getSampleRelations, getSimilarSamples } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleRelations: vi.fn(),
    getSimilarSamples: vi.fn(),
}));

vi.mock("../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../src/api/modules");
    return { ...actual, getModule };
});

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
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
 * Every panel's tab title, read from dockview's tab markup, which leaves out same-named controls
 * inside a panel's body, such as the Cloud panel's Samples and Modules buttons.
 */
function panelTabTitles(): string[] {
    return Array.from(document.querySelectorAll(".dv-default-tab-content")).map((element) => element.textContent);
}

/**
 * Closes one panel through its tab and waits for the shell to save the arrangement without it,
 * which dockview reports a moment after the close.
 */
async function closePanelAndSave(title: string): Promise<void> {
    fireEvent.click(screen.getByRole("button", { name: `Close ${title}` }));
    await waitFor(() => {
        expect(localStorage.getItem(LAYOUT_STORAGE_KEY)).not.toBeNull();
    });
}

/** The title of whichever panel is in front of each of the shell's tab groups. */
function activeTabTitles(): string[] {
    return Array.from(document.querySelectorAll(".dv-active-tab .dv-default-tab-content")).map(
        (element) => element.textContent,
    );
}

describe("WorkspaceShell", () => {
    it("mounts every default panel", () => {
        renderShellAt("/");

        const titles = panelTabTitles();
        for (const title of [
            "Modules",
            "Samples",
            "Cloud",
            "Waveform",
            "Morph",
            "Module Detail",
            "Sample Detail",
            "Stats",
        ]) {
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

    it("brings Sample Detail forward when a sample is opened", async () => {
        getSample.mockRejectedValue(new Error("no catalog behind this test"));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);

        renderShellAt("/samples/abc");

        await waitFor(() => {
            expect(activeTabTitles()).toContain("Sample Detail");
        });
    });

    it("renders the theme picker in the toolbar", () => {
        renderShellAt("/");

        expect(screen.getByLabelText("Theme")).toBeInTheDocument();
    });

    it("keeps a panel closed across a reload once a person closed it", async () => {
        const first = renderShellAt("/");
        await closePanelAndSave("Morph");
        expect(panelTabTitles()).not.toContain("Morph");
        first.unmount();

        renderShellAt("/");

        expect(panelTabTitles()).not.toContain("Morph");
    });

    it("opens a panel registered since the arrangement was saved", async () => {
        const first = renderShellAt("/");
        await closePanelAndSave("Morph");
        first.unmount();
        const knownBefore = Object.keys(PANEL_REGISTRY).filter((id) => id !== "morph");
        localStorage.setItem(KNOWN_PANELS_STORAGE_KEY, JSON.stringify(knownBefore));

        renderShellAt("/");

        expect(panelTabTitles()).toContain("Morph");
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
