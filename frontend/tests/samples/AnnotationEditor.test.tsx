import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type { SampleDetail } from "../../src/api/samples";
import { AnnotationEditor } from "../../src/samples/AnnotationEditor";
import { useAnnotationStore } from "../../src/samples/annotationStore";

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
        playback_rate_hz: null,
        duration_seconds: 0.1,
        playback_rates: [],
        equivalence_member_count: 1,
        ...overrides,
    };
}

function resolvesTo(annotation: CurationApi.AnnotationDecisions | null, hashes: readonly string[]): void {
    setSampleAnnotation.mockResolvedValue({ annotation, sample_hashes: hashes });
}

describe("AnnotationEditor", () => {
    it("saves the wording a person typed for this sample alone", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "warm pad" }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample()} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad{Enter}");

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, label: "warm pad" }, "sample");
        });
    });

    it("records what was written so every row showing those samples updates at once", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "snare" }, [SAMPLE_HASH, OTHER_HASH]);
        render(<AnnotationEditor sample={buildSample({ equivalence_member_count: 2 })} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "snare{Enter}");

        await waitFor(() => {
            expect(useAnnotationStore.getState().annotationBySampleHash[OTHER_HASH]?.label).toBe("snare");
        });
    });

    it("writes a rating the moment a star is clicked, without waiting for a save", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, rating: 4 }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample()} />);

        await userEvent.click(screen.getByRole("button", { name: "Rate 4" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, rating: 4 }, "sample");
        });
    });

    it("takes a rating back when the star it already sits at is clicked again", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo(null, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample({ rating: 3 })} />);

        await userEvent.click(screen.getByRole("button", { name: "Rate 3" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, NOTHING, "sample");
        });
    });

    it("keeps the wording a sample already carries when only its rating changes", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ label: "warm pad", rating: 5, favorite: false }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample({ hand_label: "warm pad" })} />);

        await userEvent.click(screen.getByRole("button", { name: "Rate 5" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(
                SAMPLE_HASH,
                { label: "warm pad", rating: 5, favorite: false },
                "sample",
            );
        });
    });

    it("marks a favorite on its own click", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, favorite: true }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample()} />);

        await userEvent.click(screen.getByRole("button", { name: "Favorite" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, favorite: true }, "sample");
        });
    });

    it("shows a favorite the server already knows about as pressed", () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<AnnotationEditor sample={buildSample({ favorite: true })} />);

        expect(screen.getByRole("button", { name: "Favorite" })).toHaveAttribute("aria-pressed", "true");
    });

    it("reaches a whole group by default, since that is how the listing browses them", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "snare" }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample({ equivalence_member_count: 3 })} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "snare{Enter}");

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(
                SAMPLE_HASH,
                { ...NOTHING, label: "snare" },
                "equivalence_class",
            );
        });
    });

    it("carries the group scope through a rating too, not only a label", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, rating: 2 }, [SAMPLE_HASH, OTHER_HASH]);
        render(<AnnotationEditor sample={buildSample({ equivalence_member_count: 2 })} />);

        await userEvent.click(screen.getByRole("button", { name: "Rate 2" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(
                SAMPLE_HASH,
                { ...NOTHING, rating: 2 },
                "equivalence_class",
            );
        });
    });

    it("narrows to the one sample when the group box is unticked", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "snare" }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample({ equivalence_member_count: 3 })} />);

        await userEvent.click(screen.getByRole("checkbox"));
        await userEvent.type(screen.getByLabelText("Hand label"), "snare{Enter}");

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, label: "snare" }, "sample");
        });
    });

    it("offers no group choice for a sample with no near-duplicates", () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<AnnotationEditor sample={buildSample()} />);

        expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    });

    it("records the wording when the field is left, so a thought finished is a thought saved", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "warm pad" }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample()} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad");
        await userEvent.tab();

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, label: "warm pad" }, "sample");
        });
    });

    it("writes nothing for a field left as it was found", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<AnnotationEditor sample={buildSample({ hand_label: "warm pad" })} />);

        await userEvent.click(screen.getByLabelText("Hand label"));
        await userEvent.tab();

        expect(setSampleAnnotation).not.toHaveBeenCalled();
    });

    it("puts back the wording a sample already carries when a draft is abandoned", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<AnnotationEditor sample={buildSample({ hand_label: "warm pad" })} />);

        await userEvent.type(screen.getByLabelText("Hand label"), " and bright{Escape}");

        expect(screen.getByLabelText("Hand label")).toHaveValue("warm pad");
        expect(setSampleAnnotation).not.toHaveBeenCalled();
    });

    it("offers clearing only once there is something to clear", () => {
        getLabelVocabulary.mockResolvedValue([]);
        render(<AnnotationEditor sample={buildSample({ hand_label: "warm pad" })} />);

        expect(screen.getByRole("button", { name: "Clear" })).toBeEnabled();
    });

    it("clears the wording while leaving the rating standing", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, rating: 4 }, [SAMPLE_HASH]);
        render(<AnnotationEditor sample={buildSample({ hand_label: "warm pad", rating: 4 })} />);

        await userEvent.click(screen.getByRole("button", { name: "Clear" }));

        await waitFor(() => {
            expect(setSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, { ...NOTHING, rating: 4 }, "sample");
        });
    });

    it("reports a refused write rather than pretending it landed", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        setSampleAnnotation.mockRejectedValue(new Error("request failed with status 404"));
        render(<AnnotationEditor sample={buildSample()} />);

        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad{Enter}");

        expect(await screen.findByText(/request failed with status 404/)).toBeInTheDocument();
    });
});
