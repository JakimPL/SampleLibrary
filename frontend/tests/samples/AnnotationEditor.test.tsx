import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type { SampleDetail } from "../../src/api/samples";
import { AnnotationEditor } from "../../src/samples/AnnotationEditor";
import { AnnotationRows } from "../../src/samples/AnnotationRows";
import { useAnnotationStore } from "../../src/samples/annotationStore";

const { changeSampleAnnotation, getLabelVocabulary } = vi.hoisted(() => ({
    changeSampleAnnotation: vi.fn(),
    getLabelVocabulary: vi.fn(),
}));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, changeSampleAnnotation, getLabelVocabulary };
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
        suggestions: [],
        ...overrides,
    };
}

function resolvesTo(annotation: CurationApi.AnnotationDecisions | null, hashes: readonly string[]): void {
    changeSampleAnnotation.mockResolvedValue({
        samples: hashes.map((sampleHash) => ({ sample_hash: sampleHash, annotation })),
        skipped: [],
    });
}

function renderEditor(sample: SampleDetail, scope: CurationApi.AnnotationScope = "sample"): void {
    render(<AnnotationEditor sample={sample} scope={scope} onScopeChange={() => undefined} />);
}

describe("AnnotationEditor", () => {
    it("saves the wording a person typed", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "WARM PAD" }, [SAMPLE_HASH]);
        renderEditor(buildSample());

        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad{Enter}");

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { label: "warm pad" });
        });
    });

    it("records what was written so every row showing those samples updates at once", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "SNARE" }, [SAMPLE_HASH, OTHER_HASH]);
        renderEditor(buildSample({ equivalence_member_count: 2 }), "equivalence_class");

        await userEvent.type(screen.getByLabelText("Hand label"), "snare{Enter}");

        await waitFor(() => {
            expect(useAnnotationStore.getState().annotationBySampleHash[OTHER_HASH]?.label).toBe("SNARE");
        });
    });

    it("sends a star click as the rating alone", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ label: "WARM PAD", rating: 4, favorite: false }, [SAMPLE_HASH]);
        renderEditor(buildSample({ hand_label: "WARM PAD" }));

        await userEvent.click(screen.getByRole("button", { name: "Rate 4" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { rating: 4 });
        });
    });

    it("takes a rating back when the star it already sits at is clicked again", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo(null, [SAMPLE_HASH]);
        renderEditor(buildSample({ rating: 3 }));

        await userEvent.click(screen.getByRole("button", { name: "Rate 3" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { rating: null });
        });
    });

    it("marks a favorite on its own click", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, favorite: true }, [SAMPLE_HASH]);
        renderEditor(buildSample());

        await userEvent.click(screen.getByRole("button", { name: "Favorite" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { favorite: true });
        });
    });

    it("shows a favorite the server already knows about as pressed", () => {
        getLabelVocabulary.mockResolvedValue([]);
        renderEditor(buildSample({ favorite: true }));

        expect(screen.getByRole("button", { name: "Favorite" })).toHaveAttribute("aria-pressed", "true");
    });

    it("shows a rating the moment its star is clicked, before the server answers", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        changeSampleAnnotation.mockReturnValue(new Promise(() => undefined));
        renderEditor(buildSample());

        await userEvent.click(screen.getByRole("button", { name: "Rate 2" }));

        expect(screen.getByRole("button", { name: "Rate 2" })).toHaveAttribute("aria-pressed", "true");
    });

    it("carries the group scope through a rating", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, rating: 2 }, [SAMPLE_HASH, OTHER_HASH]);
        renderEditor(buildSample({ equivalence_member_count: 2 }), "equivalence_class");

        await userEvent.click(screen.getByRole("button", { name: "Rate 2" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "equivalence_class", { rating: 2 });
        });
    });

    it("offers no group choice for a sample with no near-duplicates", () => {
        getLabelVocabulary.mockResolvedValue([]);
        renderEditor(buildSample());

        expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    });

    it("records the wording when the field is left, so a thought finished is a thought saved", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "WARM PAD" }, [SAMPLE_HASH]);
        renderEditor(buildSample());

        await userEvent.type(screen.getByLabelText("Hand label"), "warm pad");
        await userEvent.tab();

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { label: "warm pad" });
        });
    });

    it("writes nothing for a field left as it was found", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        renderEditor(buildSample({ hand_label: "warm pad" }));

        await userEvent.click(screen.getByLabelText("Hand label"));
        await userEvent.tab();

        expect(changeSampleAnnotation).not.toHaveBeenCalled();
    });

    it("puts back the wording a sample already carries when a draft is abandoned", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        renderEditor(buildSample({ hand_label: "warm pad" }));

        await userEvent.type(screen.getByLabelText("Hand label"), " and bright{Escape}");

        expect(screen.getByLabelText("Hand label")).toHaveValue("warm pad");
        expect(changeSampleAnnotation).not.toHaveBeenCalled();
    });

    it("offers clearing only once there is something to clear", () => {
        getLabelVocabulary.mockResolvedValue([]);
        renderEditor(buildSample({ hand_label: "warm pad" }));

        expect(screen.getByRole("button", { name: "Clear" })).toBeEnabled();
    });

    it("clears the wording alone", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, rating: 4 }, [SAMPLE_HASH]);
        renderEditor(buildSample({ hand_label: "warm pad", rating: 4 }));

        await userEvent.click(screen.getByRole("button", { name: "Clear" }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { label: null });
        });
    });

    it("reports a refused write and takes the change back off the screen", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        changeSampleAnnotation.mockRejectedValue(new Error("request failed with status 404"));
        renderEditor(buildSample());

        await userEvent.click(screen.getByRole("button", { name: "Rate 5" }));

        expect(await screen.findByText(/request failed with status 404/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Rate 5" })).toHaveAttribute("aria-pressed", "false");
    });
});

describe("AnnotationRows", () => {
    function renderRows(sample: SampleDetail): void {
        render(
            <dl>
                <AnnotationRows sample={sample} />
            </dl>,
        );
    }

    it("reaches a whole group by default, since that is how the listing browses them", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "SNARE" }, [SAMPLE_HASH]);
        renderRows(buildSample({ equivalence_member_count: 3 }));

        await userEvent.type(screen.getByLabelText("Hand label"), "snare{Enter}");

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "equivalence_class", { label: "snare" });
        });
    });

    it("sends a clicked suggestion to this sample alone once the group box is unticked", async () => {
        getLabelVocabulary.mockResolvedValue([]);
        resolvesTo({ ...NOTHING, label: "SNARE" }, [SAMPLE_HASH]);
        renderRows(buildSample({ equivalence_member_count: 3, suggestions: [{ label: "SNARE", score: 0.5 }] }));

        await userEvent.click(screen.getByRole("checkbox"));
        await userEvent.click(screen.getByRole("button", { name: /SNARE/ }));

        await waitFor(() => {
            expect(changeSampleAnnotation).toHaveBeenCalledWith(SAMPLE_HASH, "sample", { label: "SNARE" });
        });
    });
});
