import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type { SampleSummary } from "../../src/api/samples";
import { SampleRow } from "../../src/samples/SampleRow";
import { useSelectionStore } from "../../src/workspace/selectionStore";

const { changeSampleAnnotation, getLabelVocabulary } = vi.hoisted(() => ({
    changeSampleAnnotation: vi.fn(),
    getLabelVocabulary: vi.fn(),
}));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, changeSampleAnnotation, getLabelVocabulary };
});

const NOTHING = { label: null, rating: null, favorite: false };

function resolvesTo(annotation: CurationApi.AnnotationDecisions | null): void {
    changeSampleAnnotation.mockResolvedValue({ samples: [{ sample_hash: "abc123", annotation }], skipped: [] });
}

function buildSample(overrides: Partial<SampleSummary> = {}): SampleSummary {
    return {
        hash: "abc123",
        display_name: "kick",
        category: "kick",
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
        ...overrides,
    };
}

interface RowOverrides {
    readonly sample?: SampleSummary;
    readonly groupByEquivalence?: boolean;
}

function renderRow(overrides: RowOverrides = {}): ReturnType<typeof render> {
    getLabelVocabulary.mockResolvedValue([]);
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route
                    path="/"
                    element={
                        <table>
                            <tbody>
                                <SampleRow
                                    sample={overrides.sample ?? buildSample()}
                                    groupByEquivalence={overrides.groupByEquivalence ?? false}
                                />
                            </tbody>
                        </table>
                    }
                />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("SampleRow", () => {
    it("a plain click on the name highlights the sample without navigating to its own route", () => {
        renderRow();

        fireEvent.click(screen.getByRole("link", { name: /kick/ }));

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "abc123" });
        expect(screen.queryByText("sample route")).not.toBeInTheDocument();
    });

    it("a double-click still navigates to the sample's own route", async () => {
        renderRow();

        fireEvent.doubleClick(screen.getByRole("link", { name: /kick/ }));

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });

    it("names a sample from the listing itself, without opening it first", async () => {
        resolvesTo({ ...NOTHING, label: "WARM PAD" });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad{Enter}");

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { label: "warm pad" });
        });
    });

    it("takes a hand label back when the field is emptied, leaving the guess showing", async () => {
        resolvesTo(null);
        renderRow({ sample: buildSample({ hand_label: "warm pad" }) });

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.clear(screen.getByLabelText("Hand label"));
        await userEvent.keyboard("{Enter}");

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { label: null });
        });
        expect(await screen.findByText("Kick")).toBeInTheDocument();
    });

    it("rates a sample from the listing by sending the rating alone", async () => {
        resolvesTo({ label: "WARM PAD", rating: 4, favorite: false });
        renderRow({ sample: buildSample({ hand_label: "WARM PAD" }) });

        await userEvent.click(screen.getByRole("button", { name: "Rate 4" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { rating: 4 });
        });
    });

    it("marks a favorite from the listing", async () => {
        resolvesTo({ ...NOTHING, favorite: true });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Favorite" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "sample", { favorite: true });
        });
    });

    it("reaches every near-duplicate while the listing groups them", async () => {
        resolvesTo({ ...NOTHING, rating: 2 });
        renderRow({ sample: buildSample({ equivalence_member_count: 3 }), groupByEquivalence: true });

        await userEvent.click(screen.getByRole("button", { name: "Rate 2" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith("abc123", "equivalence_class", { rating: 2 });
        });
    });

    it("says in the row when a change could not be saved", async () => {
        changeSampleAnnotation.mockRejectedValue(new Error("request failed with status 500"));
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Rate 3" }));

        expect(await screen.findByRole("alert")).toHaveAttribute("title", "request failed with status 500");
        expect(screen.getByRole("button", { name: "Rate 3" })).toHaveAttribute("aria-pressed", "false");
    });

    it("sends a label and a star given in quick succession one after the other, each naming its own decision", async () => {
        let answerLabel: (written: CurationApi.AnnotationsWritten) => void = () => undefined;
        changeSampleAnnotation
            .mockImplementationOnce(
                () =>
                    new Promise<CurationApi.AnnotationsWritten>((resolve) => {
                        answerLabel = resolve;
                    }),
            )
            .mockResolvedValueOnce({
                samples: [{ sample_hash: "abc123", annotation: { label: "BASS", rating: 5, favorite: false } }],
                skipped: [],
            });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.type(screen.getByLabelText("Hand label"), "bass{Enter}");
        await userEvent.click(screen.getByRole("button", { name: "Rate 5" }));

        expect(changeSampleAnnotation).toHaveBeenCalledTimes(1);
        answerLabel({
            samples: [{ sample_hash: "abc123", annotation: { label: "BASS", rating: null, favorite: false } }],
            skipped: [],
        });

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenLastCalledWith("abc123", "sample", { rating: 5 });
        });
        expect(await screen.findByText("BASS")).toBeInTheDocument();
    });

    it("fills the heart under the pointer, showing what the click would leave behind", async () => {
        renderRow();

        await userEvent.hover(screen.getByRole("button", { name: "Favorite" }));

        expect(screen.getByRole("button", { name: "Favorite" })).toHaveClass("is-filled");
        expect(screen.getByRole("button", { name: "Favorite" })).toHaveAttribute("aria-pressed", "false");
    });

    it("fills every star up to the one being pointed at", async () => {
        renderRow();

        await userEvent.hover(screen.getByRole("button", { name: "Rate 4" }));

        expect(screen.getByRole("button", { name: "Rate 1" })).toHaveClass("is-filled");
        expect(screen.getByRole("button", { name: "Rate 4" })).toHaveClass("is-filled");
        expect(screen.getByRole("button", { name: "Rate 5" })).not.toHaveClass("is-filled");
    });
});
