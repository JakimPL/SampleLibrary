import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type { SampleDetail } from "../../src/api/samples";
import { LabelEditor } from "../../src/samples/LabelEditor";
import { useLabelStore } from "../../src/samples/labelStore";

const { setSampleAnnotation, getLabelVocabulary } = vi.hoisted(() => ({
    setSampleAnnotation: vi.fn(),
    getLabelVocabulary: vi.fn(),
}));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, setSampleAnnotation, getLabelVocabulary };
});

const SAMPLE_HASH = "a".repeat(64);
const OTHER_HASH = "b".repeat(64);
const NOTHING = { label: null, rating: null, favorite: false };

function buildSample(overrides: Partial<SampleDetail> = {}): SampleDetail {
    return {
        hash: SAMPLE_HASH,
        depth: 16,
        channels: 1,
        frames: 4096,
        occurrences: [],
        size_bytes: 8192,
        display_name: "smp01",
        category: "uncategorized",
        hand_label: null,
        rating: null,
        favorite: false,
        dominant_rate_hz: null,
        duration_seconds: 0.1,
        notes_played: [],
        equivalence_member_count: 1,
        ...overrides,
    };
}

describe("LabelEditor", () => {
    it("saves the wording a person typed for this sample alone", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        setSampleAnnotation.mockResolvedValue({
            annotation: { ...NOTHING, label: "warm pad" },
            sample_hashes: [SAMPLE_HASH],
        });
        render(<LabelEditor sample={buildSample()} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad");
        await userEvent.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, label: "warm pad" }, "sample");
        });
    });

    it("records what was written so every row showing those samples updates at once", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        setSampleAnnotation.mockResolvedValue({
            annotation: { ...NOTHING, label: "snare" },
            sample_hashes: [SAMPLE_HASH, OTHER_HASH],
        });
        render(<LabelEditor sample={buildSample({ equivalence_member_count: 2 })} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "snare");
        await userEvent.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(useLabelStore.getState().labelBySampleHash[OTHER_HASH]).toBe("snare");
        });
    });

    it("reaches a whole group by default, since that is how the listing browses them", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        setSampleAnnotation.mockResolvedValue({
            annotation: { ...NOTHING, label: "snare" },
            sample_hashes: [SAMPLE_HASH],
        });
        render(<LabelEditor sample={buildSample({ equivalence_member_count: 3 })} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "snare");
        await userEvent.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(
                SAMPLE_HASH,
                { ...NOTHING, label: "snare" },
                "equivalence_class",
            );
        });
    });

    it("narrows to the one sample when the group box is unticked", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        setSampleAnnotation.mockResolvedValue({
            annotation: { ...NOTHING, label: "snare" },
            sample_hashes: [SAMPLE_HASH],
        });
        render(<LabelEditor sample={buildSample({ equivalence_member_count: 3 })} />);

        await userEvent.click(screen.getByRole("checkbox"));
        await userEvent.type(screen.getByLabelText("Hand label"), "snare");
        await userEvent.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, label: "snare" }, "sample");
        });
    });

    it("offers no group choice for a sample with no near-duplicates", () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<LabelEditor sample={buildSample()} />);

        expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    });

    it("refuses to save wording that says nothing", () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<LabelEditor sample={buildSample()} />);

        expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    });

    it("offers clearing only once there is something to clear", () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<LabelEditor sample={buildSample({ hand_label: "warm pad" })} />);

        expect(screen.getByRole("button", { name: "Clear" })).toBeEnabled();
    });

    it("takes a decision back through the same scope", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        setSampleAnnotation.mockResolvedValue({ annotation: null, sample_hashes: [SAMPLE_HASH] });
        render(<LabelEditor sample={buildSample({ hand_label: "warm pad" })} />);

        await userEvent.click(screen.getByRole("button", { name: "Clear" }));

        await waitFor(() => {
            expect(useLabelStore.getState().labelBySampleHash[SAMPLE_HASH]).toBeNull();
        });
    });

    it("reports a refused write rather than pretending it landed", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        setSampleAnnotation.mockRejectedValue(new Error("request failed with status 404"));
        render(<LabelEditor sample={buildSample()} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad");
        await userEvent.click(screen.getByRole("button", { name: "Save" }));

        expect(await screen.findByText(/request failed with status 404/)).toBeInTheDocument();
    });
});
