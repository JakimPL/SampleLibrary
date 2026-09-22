import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type { SampleSummary } from "../../src/api/samples";
import { useMorphStore } from "../../src/morph/morphStore";
import { RowActionSheet } from "../../src/samples/RowActionSheet";

const { getLabelVocabulary } = vi.hoisted(() => ({ getLabelVocabulary: vi.fn().mockResolvedValue([]) }));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, getLabelVocabulary };
});

const SAMPLE: SampleSummary = {
    hash: "abc123",
    display_name: "kick",
    category: null,
    hand_label: null,
    rating: null,
    favorite: false,
    occurrence_count: 1,
    depth: 16,
    channels: 1,
    frames: 4096,
    size_bytes: 8192,
    thumbnail: null,
    playback_rate_hz: null,
    equivalence_class_hash: null,
    equivalence_member_count: 1,
};

const NOTHING = { label: null, rating: null, favorite: false };

function renderSheet(onChange = vi.fn(), onClose = vi.fn()): void {
    render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route
                    path="/"
                    element={
                        <RowActionSheet sample={SAMPLE} decisions={NOTHING} onChange={onChange} onClose={onClose} />
                    }
                />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("RowActionSheet", () => {
    it("names the sample and offers its stars and heart at once", () => {
        const onChange = vi.fn();
        renderSheet(onChange);

        expect(screen.getByRole("dialog", { name: "kick" })).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Rate 4" }));
        fireEvent.click(screen.getByRole("button", { name: "Favorite" }));

        expect(onChange).toHaveBeenCalledWith({ rating: 4 });
        expect(onChange).toHaveBeenCalledWith({ favorite: true });
    });

    it("opens the sample from its action", async () => {
        renderSheet();

        fireEvent.click(screen.getByRole("button", { name: "Open" }));

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });

    it("makes the sample either end of the morph pair", () => {
        const onClose = vi.fn();
        renderSheet(vi.fn(), onClose);

        fireEvent.click(screen.getByRole("button", { name: "Morph from here" }));

        expect(useMorphStore.getState().first).toBe("abc123");
        expect(onClose).toHaveBeenCalled();
    });

    it("turns into the label sheet on Label", () => {
        renderSheet();

        fireEvent.click(screen.getByRole("button", { name: "Label…" }));

        expect(screen.getByRole("dialog", { name: "Label" })).toBeInTheDocument();
    });
});
