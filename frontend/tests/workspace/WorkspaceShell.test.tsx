import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../src/api/modules";
import type * as SamplesApi from "../../src/api/samples";
import { useMorphStore } from "../../src/morph/morphStore";
import { routes } from "../../src/navigation/router";
import { LAYOUT_STORAGE_KEY, type StoredLayout } from "../../src/workspace/dockviewPersistence";
import type * as ModulesListPanelModule from "../../src/workspace/panels/ModulesListPanel";
import { useSelectionStore } from "../../src/workspace/selectionStore";

const MODULES_FAILURE = "the modules panel read a page that was not there";

const { failing } = vi.hoisted(() => ({ failing: { now: false } }));

vi.mock("../../src/workspace/panels/ModulesListPanel", async () => {
    const actual = await vi.importActual<typeof ModulesListPanelModule>("../../src/workspace/panels/ModulesListPanel");
    return {
        ...actual,
        ModulesListPanel: () => {
            if (failing.now) {
                throw new Error(MODULES_FAILURE);
            }
            return <p>modules</p>;
        },
    };
});

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
    return render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [initialPath] })} />);
}

/** The record the shell saved, as the next visit reads it. */
function savedRecord(): StoredLayout {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (raw === null) {
        throw new Error("the shell saved nothing");
    }
    return JSON.parse(raw) as StoredLayout;
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
    beforeEach(() => {
        failing.now = false;
    });

    it("keeps a panel that throws to itself, leaving every other panel mounted", async () => {
        // React reports a caught error to the console itself, which the suite reads as noise.
        vi.spyOn(console, "error").mockImplementation(() => undefined);
        failing.now = true;

        renderShellAt("/modules");

        expect(await screen.findByText(MODULES_FAILURE)).toHaveAttribute("role", "alert");
        expect(panelTabTitles()).toContain("Cloud");
        expect(panelTabTitles()).toContain("Samples");
        vi.restoreAllMocks();
    });

    it("mounts every default panel", () => {
        renderShellAt("/");

        const titles = panelTabTitles();
        for (const title of ["Modules", "Samples", "Cloud", "Morph", "Module Detail", "Sample Detail", "Stats"]) {
            expect(titles).toContain(title);
        }
    });

    it("shows the player strip once a sample is focused", async () => {
        getSample.mockRejectedValue(new Error("no catalog behind this test"));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        renderShellAt("/");
        expect(screen.queryByRole("region", { name: "Player" })).not.toBeInTheDocument();

        act(() => {
            useSelectionStore.getState().focusSample("abc");
        });

        expect(await screen.findByRole("region", { name: "Player" })).toBeInTheDocument();
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
            files: [],
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

    it("renders the theme picker in the top bar", () => {
        renderShellAt("/");

        expect(screen.getByLabelText("Theme")).toBeInTheDocument();
    });

    it("brings a panel forward at its own address", async () => {
        renderShellAt("/modules");

        await waitFor(() => {
            expect(activeTabTitles()).toContain("Modules");
        });
    });

    it("opens a closed panel again when its own address is visited", async () => {
        const first = renderShellAt("/");
        await closePanelAndSave("Stats");
        first.unmount();

        renderShellAt("/stats");

        await waitFor(() => {
            expect(panelTabTitles()).toContain("Stats");
        });
    });

    it("brings the Morph panel forward once a pair is complete", async () => {
        renderShellAt("/");

        act(() => {
            useMorphStore.getState().join("a".repeat(64), "b".repeat(64));
        });

        await waitFor(() => {
            expect(activeTabTitles()).toContain("Morph");
        });
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
        const record = savedRecord();
        localStorage.setItem(
            LAYOUT_STORAGE_KEY,
            JSON.stringify({ ...record, knownPanels: record.knownPanels.filter((id) => id !== "morph") }),
        );

        renderShellAt("/");

        expect(panelTabTitles()).toContain("Morph");
    });

    it("lets a closed panel be reopened through the View menu", async () => {
        renderShellAt("/");
        expect(panelTabTitles()).toContain("Stats");

        fireEvent.click(screen.getByRole("button", { name: "Close Stats" }));
        expect(panelTabTitles()).not.toContain("Stats");

        fireEvent.click(screen.getByText("View"));
        fireEvent.click(await screen.findByRole("checkbox", { name: "Stats" }));

        await waitFor(() => {
            expect(panelTabTitles()).toContain("Stats");
        });
    });
});
