import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../src/api/cloud";
import type { SimilarSample } from "../../src/api/samples";
import { COARSE_POINTER_MEDIA_QUERY } from "../../src/layout/layoutMode";
import { SimilarSampleRow } from "../../src/samples/SimilarSampleRow";
import { useAudioPreview } from "../../src/samples/useAudioPreview";
import { useSelectionStore } from "../../src/workspace/selectionStore";
import { stubMatchMedia } from "../support/matchMedia";

const { getCategoryTags } = vi.hoisted(() => ({ getCategoryTags: vi.fn().mockResolvedValue([]) }));

vi.mock("../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../src/api/cloud");
    return { ...actual, getCategoryTags };
});

function buildSimilar(overrides: Partial<SimilarSample> = {}): SimilarSample {
    return {
        hash: "def456",
        distance: 0.125,
        playback_rate_hz: null,
        display_name: "kick_808",
        category: "BASS DRUM",
        hand_label: null,
        thumbnail: null,
        ...overrides,
    };
}

function renderRow(similar: SimilarSample = buildSimilar()): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route
                    path="/"
                    element={
                        <table>
                            <tbody>
                                <SimilarSampleRow similar={similar} />
                            </tbody>
                        </table>
                    }
                />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

/** The shared preview, silenced, so a test reads only the sound its own tap makes. */
function silentPreview(): ReturnType<typeof renderHook<ReturnType<typeof useAudioPreview>, unknown>> {
    const preview = renderHook(() => useAudioPreview());
    act(() => {
        preview.result.current.stop();
    });
    return preview;
}

describe("SimilarSampleRow", () => {
    it("names the neighbor over its short hash, with what it is and how far it sits", () => {
        renderRow();

        const link = screen.getByRole("link", { name: /kick_808/ });
        expect(link).toHaveTextContent("def456");
        expect(link).toHaveTextContent("BASS DRUM");
        expect(screen.getByText("0.125")).toBeInTheDocument();
    });

    it("keeps a pointer's click to the highlight", () => {
        renderRow();
        const preview = silentPreview();

        fireEvent.click(screen.getByRole("link", { name: /kick_808/ }), { detail: 1 });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "def456" });
        expect(preview.result.current.playingKey).toBeNull();
    });

    it("takes the neighbor in hand and plays it at its rate on a finger's tap", () => {
        stubMatchMedia(new Set([COARSE_POINTER_MEDIA_QUERY]));
        renderRow(buildSimilar({ playback_rate_hz: 8363 }));
        const preview = silentPreview();

        fireEvent.click(screen.getByRole("link", { name: /kick_808/ }), { detail: 1 });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "def456" });
        expect(preview.result.current.source).toMatchObject({ key: "def456", playbackRateHz: 8363 });
        expect(preview.result.current.playingKey).toBe("def456");
    });

    it("plays the neighbor from a plain play button while no thumbnail is stored", () => {
        const { container } = renderRow();

        const button = screen.getByRole("button", { name: "Play sample preview" });
        fireEvent.click(button);

        expect(button).toHaveAttribute("aria-pressed", "true");
        expect(container.querySelector("canvas")).not.toBeInTheDocument();
    });

    it("draws the stored thumbnail as the play button", () => {
        const { container } = renderRow(buildSimilar({ thumbnail: [{ minimum: -0.5, maximum: 0.5 }] }));

        expect(container.querySelector("canvas")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Play sample preview" })).toBeInTheDocument();
    });
});
