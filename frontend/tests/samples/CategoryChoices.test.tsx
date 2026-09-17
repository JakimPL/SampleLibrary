import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type { SampleDetail } from "../../src/api/samples";
import { CategoryChoices, NO_CATEGORIES } from "../../src/samples/CategoryChoices";

const { changeSampleAnnotation } = vi.hoisted(() => ({
    changeSampleAnnotation: vi.fn(),
}));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, changeSampleAnnotation };
});

const SAMPLE_HASH = "a".repeat(64);
const NOTHING = { label: null, rating: null, favorite: false };
const CATEGORIES = [
    { label: "BASS DRUM", score: 0.81 },
    { label: "SNARE", score: 0.4 },
];

function buildSample(overrides: Partial<SampleDetail> = {}): SampleDetail {
    return {
        hash: SAMPLE_HASH,
        depth: 16,
        channels: 1,
        frames: 4096,
        occurrences: [],
        files: [],
        size_bytes: 8192,
        display_name: "smp01",
        suggested_label: null,
        hand_label: null,
        rating: null,
        favorite: false,
        playback_rate_hz: null,
        duration_seconds: 0.1,
        playback_rates: [],
        equivalence_member_count: 1,
        suggestions: CATEGORIES,
        ...overrides,
    };
}

function resolvesTo(label: string): void {
    changeSampleAnnotation.mockResolvedValue({
        samples: [{ sample_hash: SAMPLE_HASH, annotation: { ...NOTHING, label } }],
        skipped: [],
    });
}

describe("CategoryChoices", () => {
    it("shows each category with its score, closest first", () => {
        render(<CategoryChoices sample={buildSample()} scope="sample" />);

        const buttons = screen.getAllByRole("button");
        expect(buttons.map((button) => button.textContent)).toEqual(["BASS DRUM0.81", "SNARE0.40"]);
    });

    it("writes a clicked category as the label of a sample that had none", async () => {
        resolvesTo("BASS DRUM");
        render(<CategoryChoices sample={buildSample()} scope="sample" />);

        await userEvent.click(screen.getByRole("button", { name: /BASS DRUM/ }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { label: "BASS DRUM" });
        });
    });

    it("appends a clicked category after the wording the sample already carries, and changes the label alone", async () => {
        resolvesTo("LO-FI, BASS DRUM");
        render(<CategoryChoices sample={buildSample({ hand_label: "LO-FI", rating: 4 })} scope="sample" />);

        await userEvent.click(screen.getByRole("button", { name: /BASS DRUM/ }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { label: "LO-FI, BASS DRUM" });
        });
    });

    it("shows a category the label already holds as taken, and writes nothing for it", () => {
        render(<CategoryChoices sample={buildSample({ hand_label: "snare" })} scope="sample" />);

        const taken = screen.getByRole("button", { name: /SNARE/ });
        expect(taken).toHaveAttribute("aria-pressed", "true");
        expect(taken).toBeDisabled();
        expect(changeSampleAnnotation).not.toHaveBeenCalled();
    });

    it("reaches as far as the scope it is given", async () => {
        resolvesTo("SNARE");
        render(<CategoryChoices sample={buildSample({ equivalence_member_count: 3 })} scope="equivalence_class" />);

        await userEvent.click(screen.getByRole("button", { name: /SNARE/ }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "equivalence_class", { label: "SNARE" });
        });
    });

    it("says so when no scoring has reached the sample", () => {
        render(<CategoryChoices sample={buildSample({ suggestions: [] })} scope="sample" />);

        expect(screen.getByText(NO_CATEGORIES)).toBeInTheDocument();
    });
});
