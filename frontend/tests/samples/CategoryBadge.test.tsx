import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryBadge } from "../../src/samples/CategoryBadge";
import { useLabelStore } from "../../src/samples/labelStore";

const SAMPLE_HASH = "a".repeat(64);

describe("CategoryBadge", () => {
    it("names the guessed category when nobody has labeled the sample", () => {
        render(<CategoryBadge sampleHash={SAMPLE_HASH} category="kick" handLabel={null} />);

        expect(screen.getByText("Kick")).toBeInTheDocument();
    });

    it("shows what a person decided in place of what was guessed", () => {
        render(<CategoryBadge sampleHash={SAMPLE_HASH} category="kick" handLabel="dirty 909" />);

        expect(screen.getByText("dirty 909")).toBeInTheDocument();
        expect(screen.queryByText("Kick")).not.toBeInTheDocument();
    });

    it("prefers a label set in this session over the one the server sent", () => {
        useLabelStore.getState().applyLabel([SAMPLE_HASH], "rimshot");

        render(<CategoryBadge sampleHash={SAMPLE_HASH} category="kick" handLabel="dirty 909" />);

        expect(screen.getByText("rimshot")).toBeInTheDocument();
    });

    it("falls back to the guess once a label is cleared in this session", () => {
        useLabelStore.getState().applyLabel([SAMPLE_HASH], null);

        render(<CategoryBadge sampleHash={SAMPLE_HASH} category="kick" handLabel="dirty 909" />);

        expect(screen.getByText("Kick")).toBeInTheDocument();
    });

    it("leaves a sample nobody labeled in this session alone", () => {
        useLabelStore.getState().applyLabel(["b".repeat(64)], "rimshot");

        render(<CategoryBadge sampleHash={SAMPLE_HASH} category="snare" handLabel={null} />);

        expect(screen.getByText("Snare")).toBeInTheDocument();
    });
});
