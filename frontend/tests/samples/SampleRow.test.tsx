import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { SampleSummary } from "../../src/api/samples";
import { SampleRow } from "../../src/samples/SampleRow";
import { useSelectionStore } from "../../src/workspace/selectionStore";

function buildSample(): SampleSummary {
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
        dominant_rate_hz: null,
        dominant_note: null,
        equivalence_class_hash: null,
        equivalence_member_count: 1,
    };
}

function renderRow(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route
                    path="/"
                    element={
                        <table>
                            <tbody>
                                <SampleRow sample={buildSample()} />
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
});
