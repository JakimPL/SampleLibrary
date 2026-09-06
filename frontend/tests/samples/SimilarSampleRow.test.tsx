import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { SimilarSample } from "../../src/api/samples";
import { SimilarSampleRow } from "../../src/samples/SimilarSampleRow";

function buildSimilar(): SimilarSample {
    return { hash: "def456", distance: 0.125 };
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
                                <SimilarSampleRow similar={buildSimilar()} />
                            </tbody>
                        </table>
                    }
                />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

describe("SimilarSampleRow", () => {
    it("renders the neighbor's short hash and distance", () => {
        renderRow();

        expect(screen.getByRole("link", { name: /def456/ })).toBeInTheDocument();
        expect(screen.getByText("0.125")).toBeInTheDocument();
    });

    it("the play button plays the row's own sample", () => {
        renderRow();

        const button = screen.getByRole("button", { name: "Play sample preview" });
        fireEvent.click(button);

        expect(button).toHaveAttribute("aria-pressed", "true");
    });
});
