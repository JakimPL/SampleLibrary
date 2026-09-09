import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type { SampleSummary } from "../../src/api/samples";
import { SampleRow } from "../../src/samples/SampleRow";
import { useSelectionStore } from "../../src/workspace/selectionStore";

const { setSampleAnnotation, getLabelVocabulary } = vi.hoisted(() => ({
    setSampleAnnotation: vi.fn(),
    getLabelVocabulary: vi.fn(),
}));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, setSampleAnnotation, getLabelVocabulary };
});

const NOTHING = { label: null, rating: null, favorite: false };

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
    // Regression test for a real bug: the row's own click handler sat on the `<tr>`, attached with
    // `onClick`, while the name it wraps is its own `<Link>` one level in. A bubble-phase handler on
    // the row runs only after that inner `<Link>`'s own bubble-phase handler already read
    // `event.defaultPrevented` and navigated -- calling `preventDefault` from the row was already too
    // late to stop it. Every plain click on a sample's name therefore navigated to its route in
    // addition to highlighting it, which fired the shell's route-param focus effect as a second,
    // independent write to the same highlight moments after the row's own -- the two-write race this
    // codebase's Cloud panel actually crashed on. `onClickCapture` (see `useEntityRowInteractions`'s
    // docstring) is what this test locks in.
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
        setSampleAnnotation.mockResolvedValue({
            annotation: { ...NOTHING, label: "warm pad" },
            sample_hashes: ["abc123"],
        });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad{Enter}");

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith("abc123", { ...NOTHING, label: "warm pad" }, "sample");
        });
    });

    it("takes a hand label back when the field is emptied, leaving the guess showing", async () => {
        setSampleAnnotation.mockResolvedValue({ annotation: null, sample_hashes: ["abc123"] });
        renderRow({ sample: buildSample({ hand_label: "warm pad" }) });

        await userEvent.click(screen.getByRole("button", { name: "Edit category" }));
        await userEvent.clear(screen.getByLabelText("Hand label"));
        await userEvent.keyboard("{Enter}");

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith("abc123", NOTHING, "sample");
        });
        expect(await screen.findByText("Kick")).toBeInTheDocument();
    });

    it("rates a sample from the listing, keeping the wording it already carries", async () => {
        setSampleAnnotation.mockResolvedValue({
            annotation: { label: "warm pad", rating: 4, favorite: false },
            sample_hashes: ["abc123"],
        });
        renderRow({ sample: buildSample({ hand_label: "warm pad" }) });

        await userEvent.click(screen.getByRole("button", { name: "Rate 4" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(
                "abc123",
                { label: "warm pad", rating: 4, favorite: false },
                "sample",
            );
        });
    });

    it("marks a favorite from the listing", async () => {
        setSampleAnnotation.mockResolvedValue({
            annotation: { ...NOTHING, favorite: true },
            sample_hashes: ["abc123"],
        });
        renderRow();

        await userEvent.click(screen.getByRole("button", { name: "Favorite" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith("abc123", { ...NOTHING, favorite: true }, "sample");
        });
    });

    it("reaches every near-duplicate while the listing groups them", async () => {
        setSampleAnnotation.mockResolvedValue({ annotation: { ...NOTHING, rating: 2 }, sample_hashes: ["abc123"] });
        renderRow({ sample: buildSample({ equivalence_member_count: 3 }), groupByEquivalence: true });

        await userEvent.click(screen.getByRole("button", { name: "Rate 2" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith("abc123", { ...NOTHING, rating: 2 }, "equivalence_class");
        });
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
