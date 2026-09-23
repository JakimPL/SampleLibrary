import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ModuleDetail } from "../../src/api/modules";
import { COARSE_POINTER_MEDIA_QUERY } from "../../src/layout/layoutMode";
import { ModuleSampleRow } from "../../src/modules/ModuleSampleRow";
import { useAudioPreview } from "../../src/samples/useAudioPreview";
import { useSelectionStore } from "../../src/workspace/selectionStore";
import { stubMatchMedia } from "../support/matchMedia";

const SLOT_RATE_HZ = 8363;

const OCCURRENCE: ModuleDetail["occurrences"][number] = {
    properties: {
        sample_hash: "sample-1",
        occurrence: { module_hash: "abc", instrument_index: 0, sample_slot: 0 },
        name: "lead",
        rate: SLOT_RATE_HZ,
        volume: 64,
        tracker: "xm",
        tuning: { relative_note: 0, finetune: 0 },
    },
    sample: { hash: "sample-1", depth: 16, channels: 1, frames: 4096, size_bytes: 8192, thumbnail: null },
};

function renderRow(): void {
    render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route
                    path="/"
                    element={
                        <table>
                            <tbody>
                                <ModuleSampleRow occurrence={OCCURRENCE} />
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

describe("ModuleSampleRow", () => {
    it("takes the sample in hand on a pointer's click, leaving the sound to its thumbnail", () => {
        renderRow();
        const preview = silentPreview();

        fireEvent.click(screen.getByRole("link", { name: "lead" }), { detail: 1 });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "sample-1" });
        expect(preview.result.current.playingKey).toBeNull();
    });

    it("takes the sample in hand and plays it at its slot's rate on a finger's tap", () => {
        stubMatchMedia(new Set([COARSE_POINTER_MEDIA_QUERY]));
        renderRow();
        const preview = silentPreview();

        fireEvent.click(screen.getByRole("link", { name: "lead" }), { detail: 1 });

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "sample-1" });
        expect(preview.result.current.source).toMatchObject({ key: "sample-1", playbackRateHz: SLOT_RATE_HZ });
    });
});
