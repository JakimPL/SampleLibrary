import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../../src/api/cloud";
import type * as ModulesApi from "../../../src/api/modules";
import type * as SamplesApi from "../../../src/api/samples";
import { PHONE_MEDIA_QUERY } from "../../../src/layout/layoutMode";
import { PageBody, PageHeaderFor } from "../../../src/shell/phone/PageLayer";
import { usePhoneShellStore } from "../../../src/shell/phone/phoneShellStore";
import type { PhonePage } from "../../../src/shell/phone/phoneView";
import { useListingOrderStore } from "../../../src/workspace/listingOrderStore";
import { useSelectionStore } from "../../../src/workspace/selectionStore";
import { stubMatchMedia } from "../../support/matchMedia";

const { getSample, getSampleRelations, getSimilarSamples, getModule } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleRelations: vi.fn(),
    getSimilarSamples: vi.fn(),
    getModule: vi.fn(),
}));

const { getCategoryTags } = vi.hoisted(() => ({ getCategoryTags: vi.fn().mockResolvedValue([]) }));

vi.mock("../../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../../src/api/cloud");
    return { ...actual, getCategoryTags };
});

vi.mock("wavesurfer.js", () => ({
    default: {
        create: () => ({
            on: () => () => undefined,
            play: vi.fn().mockResolvedValue(undefined),
            pause: vi.fn(),
            setTime: vi.fn(),
            setPlaybackRate: vi.fn(),
            setOptions: vi.fn(),
            destroy: vi.fn(),
        }),
    },
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
});

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, getModule };
});

function catalogAnswers(): void {
    getSample.mockImplementation((hash: string) =>
        Promise.resolve({
            hash,
            depth: 16,
            channels: 1,
            frames: 4096,
            display_name: `sample ${hash}`,
            category: null,
            hand_label: null,
            rating: null,
            favorite: false,
            size_bytes: 8192,
            duration_seconds: 0.09,
            playback_rate_hz: 8363,
            playback_rates: [{ rate_hz: 8363, event_count: 2 }],
            categories: [],
            occurrences: [],
            files: [],
            equivalence_member_count: 1,
        }),
    );
    getSampleRelations.mockResolvedValue([]);
    getSimilarSamples.mockResolvedValue([]);
    getModule.mockResolvedValue({
        hash: "m2",
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
}

function renderHeaderAt(
    entries: readonly string[],
    page: PhonePage,
    withBody = false,
): ReturnType<typeof createMemoryRouter> {
    catalogAnswers();
    const router = createMemoryRouter(
        [
            {
                path: "*",
                element: (
                    <>
                        <header>
                            <PageHeaderFor page={page} />
                        </header>
                        {withBody && <PageBody page={page} />}
                    </>
                ),
            },
        ],
        { initialEntries: [...entries], initialIndex: entries.length - 1 },
    );
    render(<RouterProvider router={router} />);
    return router;
}

describe("PageHeaderFor", () => {
    it("names the sample and walks its listing, replacing the address", async () => {
        act(() => {
            useListingOrderStore.getState().publish("sample", ["a", "b", "c"]);
        });
        const router = renderHeaderAt(["/samples/b"], { kind: "sample", sampleHash: "b" });

        expect(await screen.findByRole("heading", { name: "sample b" })).toBeInTheDocument();
        expect(screen.getByText("2 / 3")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Next sample" }));

        await waitFor(() => {
            expect(router.state.location.pathname).toBe("/samples/c");
        });
        expect(router.state.historyAction).toBe("REPLACE");
    });

    it("rests the step at the edge of the listing", () => {
        act(() => {
            useListingOrderStore.getState().publish("sample", ["a", "b"]);
        });
        renderHeaderAt(["/samples/a"], { kind: "sample", sampleHash: "a" });

        expect(screen.getByRole("button", { name: "Previous sample" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Next sample" })).toBeEnabled();
    });

    it("keeps the steps away while the sample stands outside its listing", () => {
        renderHeaderAt(["/samples/z"], { kind: "sample", sampleHash: "z" });

        expect(screen.queryByRole("button", { name: "Next sample" })).not.toBeInTheDocument();
        expect(screen.getByText("z")).toBeInTheDocument();
    });

    it("goes back through the history once a tab has been shown", async () => {
        usePhoneShellStore.getState().rememberTab("/cloud");
        const router = renderHeaderAt(["/cloud", "/samples/b"], { kind: "sample", sampleHash: "b" });

        fireEvent.click(screen.getByRole("button", { name: "Back" }));

        await waitFor(() => {
            expect(router.state.location.pathname).toBe("/cloud");
        });
    });

    it("goes to the home tab when the visit began on the page", async () => {
        const router = renderHeaderAt(["/samples/b"], { kind: "sample", sampleHash: "b" });

        fireEvent.click(screen.getByRole("button", { name: "Back" }));

        await waitFor(() => {
            expect(router.state.location.pathname).toBe("/");
        });
        expect(router.state.historyAction).toBe("REPLACE");
    });

    it("names a module and a panel page", async () => {
        act(() => {
            useListingOrderStore.getState().publish("module", ["m1", "m2"]);
        });
        renderHeaderAt(["/modules/m2"], { kind: "module", moduleHash: "m2" });
        expect(await screen.findByRole("heading", { name: "A Song" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Previous module" })).toBeEnabled();

        renderHeaderAt(["/stats"], { kind: "panel", panelId: "stats" });
        expect(screen.getByRole("heading", { name: "Stats" })).toBeInTheDocument();
    });
});

describe("PageBody", () => {
    it("puts the sample's one-row transport over its detail", async () => {
        stubMatchMedia(new Set([PHONE_MEDIA_QUERY]));
        useSelectionStore.getState().focusSample("b");
        renderHeaderAt(["/samples/b"], { kind: "sample", sampleHash: "b" }, true);

        expect(await screen.findByRole("button", { name: "▶" })).toBeInTheDocument();
        expect(screen.queryByRole("link", { name: "Save this sample" })).not.toBeInTheDocument();
    });
});
