import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../src/api/cloud";
import type { AnnotationDecisions } from "../../src/api/curation";
import { useAnnotationStore } from "../../src/samples/annotationStore";
import { CategoryBadge } from "../../src/samples/CategoryBadge";
import { UNLABELED_SAMPLE_LABEL } from "../../src/shared/labels";
import { labelColor, readLabelPaletteParameters } from "../../src/theme/labelPalette";

const SAMPLE_HASH = "a".repeat(64);
const HI_HAT_RANK = 2;

const { getSuggestionTags } = vi.hoisted(() => ({ getSuggestionTags: vi.fn() }));

vi.mock("../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../src/api/cloud");
    return { ...actual, getSuggestionTags };
});

function confirm(sampleHash: string, annotation: AnnotationDecisions | null): void {
    useAnnotationStore
        .getState()
        .settleChange(0, [sampleHash], { samples: [{ sample_hash: sampleHash, annotation }], skipped: [] });
}

function serveTags(): void {
    getSuggestionTags.mockResolvedValue([
        { path: ["HI-HAT"], sample_count: 4, rank: HI_HAT_RANK },
        { path: ["HI-HAT", "CLOSED"], sample_count: 3, rank: HI_HAT_RANK },
    ]);
}

function badgeOf(label: string): Element | null {
    return screen.getByText(label).closest(".badge");
}

function swatchOf(label: string): Element | null {
    return badgeOf(label)?.querySelector(".badge-swatch") ?? null;
}

describe("CategoryBadge", () => {
    it("names what the listening model heard when nobody has labeled the sample", () => {
        serveTags();

        render(<CategoryBadge sampleHash={SAMPLE_HASH} suggestedLabel="HI-HAT: CLOSED" handLabel={null} />);

        expect(badgeOf("HI-HAT: CLOSED")).toHaveClass("badge-category");
        expect(badgeOf("HI-HAT: CLOSED")).toHaveAttribute("title", "HI-HAT: CLOSED");
    });

    it("wears its category's color once the tags arrive, and none before", async () => {
        serveTags();

        render(<CategoryBadge sampleHash={SAMPLE_HASH} suggestedLabel="HI-HAT: CLOSED" handLabel={null} />);

        expect(swatchOf("HI-HAT: CLOSED")).toBeNull();
        const expected = labelColor(HI_HAT_RANK, readLabelPaletteParameters());
        await vi.waitFor(() => {
            expect(swatchOf("HI-HAT: CLOSED")).toHaveStyle({ background: expected });
        });
    });

    it("shows what a person decided in place of what was heard", () => {
        serveTags();

        render(<CategoryBadge sampleHash={SAMPLE_HASH} suggestedLabel="SNARE" handLabel="dirty 909" />);

        expect(badgeOf("dirty 909")).toHaveClass("badge-hand-label");
        expect(screen.queryByText("SNARE")).not.toBeInTheDocument();
    });

    it("reads as unlabeled when neither a person nor the model named the sample", () => {
        serveTags();

        render(<CategoryBadge sampleHash={SAMPLE_HASH} suggestedLabel={null} handLabel={null} />);

        expect(badgeOf(UNLABELED_SAMPLE_LABEL)).toHaveClass("badge-unlabeled");
    });

    it("prefers a label set in this session over the one the server sent", () => {
        serveTags();
        confirm(SAMPLE_HASH, { label: "rimshot", rating: null, favorite: false });

        render(<CategoryBadge sampleHash={SAMPLE_HASH} suggestedLabel="SNARE" handLabel="dirty 909" />);

        expect(screen.getByText("rimshot")).toBeInTheDocument();
    });

    it("falls back to what was heard once a label is cleared in this session", () => {
        serveTags();
        confirm(SAMPLE_HASH, null);

        render(<CategoryBadge sampleHash={SAMPLE_HASH} suggestedLabel="SNARE" handLabel="dirty 909" />);

        expect(screen.getByText("SNARE")).toBeInTheDocument();
    });
});
