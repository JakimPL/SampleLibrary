import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../../src/api/cloud";
import type * as CurationApi from "../../../src/api/curation";
import type * as ModulesApi from "../../../src/api/modules";
import type * as SamplesApi from "../../../src/api/samples";
import { useMorphStore } from "../../../src/morph/morphStore";
import { useAudioPreview } from "../../../src/samples/useAudioPreview";
import { usePhoneShellStore } from "../../../src/shell/phone/phoneShellStore";
import { Tray, useEntityInHand } from "../../../src/shell/phone/Tray";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { getSamplePreview, getSample, getSampleRelations, getSimilarSamples, getModule, getCategoryTags } = vi.hoisted(
    () => ({
        getSamplePreview: vi.fn(),
        getSample: vi.fn(),
        getSampleRelations: vi.fn(),
        getSimilarSamples: vi.fn(),
        getModule: vi.fn(),
        getCategoryTags: vi.fn(),
    }),
);
const { changeSampleAnnotation, getLabelVocabulary } = vi.hoisted(() => ({
    changeSampleAnnotation: vi.fn(),
    getLabelVocabulary: vi.fn(),
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSamplePreview, getSample, getSampleRelations, getSimilarSamples };
});

vi.mock("../../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../../src/api/modules");
    return { ...actual, getModule };
});

vi.mock("../../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../../src/api/cloud");
    return { ...actual, getCategoryTags };
});

vi.mock("../../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../../src/api/curation");
    return { ...actual, changeSampleAnnotation, getLabelVocabulary };
});

const SAMPLE_HASH = "a".repeat(64);
const MODULE_HASH = "b".repeat(64);

function catalogAnswers(): void {
    getCategoryTags.mockResolvedValue([]);
    getLabelVocabulary.mockResolvedValue([]);
    getSamplePreview.mockResolvedValue({
        display_name: "kick",
        category: "KICK",
        hand_label: null,
        thumbnail: null,
    });
    getSample.mockResolvedValue({
        hash: SAMPLE_HASH,
        depth: 16,
        channels: 1,
        frames: 4096,
        display_name: "kick",
        category: "KICK",
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
        equivalence_member_count: 3,
    });
    getSampleRelations.mockResolvedValue([]);
    getSimilarSamples.mockResolvedValue([]);
    getModule.mockResolvedValue({
        hash: MODULE_HASH,
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
    changeSampleAnnotation.mockResolvedValue({
        samples: [{ sample_hash: SAMPLE_HASH, annotation: { label: null, rating: 4, favorite: false } }],
        skipped: [],
    });
}

function renderTray(): ReturnType<typeof render> {
    catalogAnswers();
    return render(
        <MemoryRouter>
            <Tray />
        </MemoryRouter>,
    );
}

/** The tray once the sample's detail has landed, which is when its heart appears. */
async function trayWithDetail(): Promise<void> {
    renderTray();
    await screen.findByRole("button", { name: "Favorite" });
}

describe("useEntityInHand", () => {
    it("names the highlighted entity, else the focused sample, else nothing", () => {
        const { result } = renderHook(() => useEntityInHand());
        expect(result.current).toBeNull();

        act(() => {
            useSelectionStore.setState({ focusedSampleHash: "abc", highlighted: null });
        });
        expect(result.current).toEqual({ kind: "sample", hash: "abc" });

        act(() => {
            useSelectionStore.getState().highlightEntity({ kind: "module", hash: "def" });
        });
        expect(result.current).toEqual({ kind: "module", hash: "def" });
    });
});

describe("Tray", () => {
    it("shows nothing while nothing is in hand", () => {
        const { container } = renderTray();

        expect(container).toBeEmptyDOMElement();
    });

    it("names the sample in hand and offers the way to open it", async () => {
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: SAMPLE_HASH });
        renderTray();

        expect(await screen.findByText("kick")).toBeInTheDocument();
        expect(screen.getByRole("region", { name: "Sample in hand" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Open sample" })).toHaveAttribute("href", `/samples/${SAMPLE_HASH}`);
        expect(await screen.findByText("×3")).toBeInTheDocument();
    });

    it("plays the sample at its library rate, pauses it and takes it up again", async () => {
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: SAMPLE_HASH });
        await trayWithDetail();
        const { result } = renderHook(() => useAudioPreview());
        act(() => {
            result.current.stop();
        });

        fireEvent.click(screen.getByRole("button", { name: "Play sample" }));
        expect(result.current.playingKey).toBe(SAMPLE_HASH);
        expect(result.current.source?.playbackRateHz).toBe(8363);

        fireEvent.click(screen.getByRole("button", { name: "Pause sample" }));
        expect(result.current.paused).toBe(true);

        fireEvent.click(screen.getByRole("button", { name: "Play sample" }));
        expect(result.current.paused).toBe(false);
        expect(result.current.playingKey).toBe(SAMPLE_HASH);
    });

    it("marks the favorite from the tray, reaching the sample's near-duplicates", async () => {
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: SAMPLE_HASH });
        await trayWithDetail();

        fireEvent.click(screen.getByRole("button", { name: "Favorite" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "equivalence_class", { favorite: true });
        });
    });

    it("opens out to the stars, the label sheet and the morph pair", async () => {
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: SAMPLE_HASH });
        await trayWithDetail();

        fireEvent.click(screen.getByRole("button", { name: /kick/, expanded: false }));
        expect(usePhoneShellStore.getState().trayExpanded).toBe(true);

        fireEvent.click(screen.getByRole("button", { name: "Rate 4" }));
        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "equivalence_class", { rating: 4 });
        });

        fireEvent.click(screen.getByRole("button", { name: "Morph from here" }));
        expect(useMorphStore.getState().first).toBe(SAMPLE_HASH);

        fireEvent.click(screen.getByRole("button", { name: "Label…" }));
        expect(screen.getByRole("dialog", { name: "Label" })).toBeInTheDocument();
    });

    it("names the module in hand and offers the way to open it", async () => {
        useSelectionStore.getState().highlightEntity({ kind: "module", hash: MODULE_HASH });
        renderTray();

        expect(await screen.findByText("A Song")).toBeInTheDocument();
        expect(screen.getByRole("region", { name: "Module in hand" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Open module" })).toHaveAttribute("href", `/modules/${MODULE_HASH}`);
    });
});
