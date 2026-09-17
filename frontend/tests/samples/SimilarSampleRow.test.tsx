import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../src/api/cloud";
import type { SimilarSample } from "../../src/api/samples";
import { SimilarSampleRow } from "../../src/samples/SimilarSampleRow";

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
        suggested_label: "BASS DRUM",
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

describe("SimilarSampleRow", () => {
    it("names the neighbor over its short hash, with what it is and how far it sits", () => {
        renderRow();

        expect(screen.getByRole("link", { name: /kick_808/ })).toHaveTextContent("def456");
        expect(screen.getByText("BASS DRUM")).toBeInTheDocument();
        expect(screen.getByText("0.125")).toBeInTheDocument();
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
