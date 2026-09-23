import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ColoringMode } from "../../src/cloud/ColoringModeChoice";
import type { TopLevelTag } from "../../src/cloud/labelColoring";
import { LegendSheet } from "../../src/cloud/LegendSheet";

const EMPTY_CAPTION = "No sample carries a tag yet.";

const TAGS: readonly TopLevelTag[] = [
    { name: "SNARE", sampleCount: 21, rank: 0 },
    { name: "PIANO", sampleCount: 12, rank: 2 },
];

interface SheetOverrides {
    readonly tags?: readonly TopLevelTag[];
    readonly onModeChange?: (mode: ColoringMode) => void;
    readonly onToggle?: (name: string) => void;
}

function renderSheet(overrides: SheetOverrides = {}): void {
    render(
        <LegendSheet
            mode="category"
            onModeChange={overrides.onModeChange ?? vi.fn()}
            tags={overrides.tags ?? TAGS}
            painted={["SNARE"]}
            onToggle={overrides.onToggle ?? vi.fn()}
            emptyCaption={EMPTY_CAPTION}
            onClose={vi.fn()}
        />,
    );
}

describe("LegendSheet", () => {
    it("offers the choice of what paints the points above the chips", () => {
        const onModeChange = vi.fn();
        renderSheet({ onModeChange });

        const choice = screen.getByRole("group", { name: "Color by" });
        expect(within(choice).getByRole("button", { name: "Category" })).toHaveAttribute("aria-pressed", "true");
        fireEvent.click(within(choice).getByRole("button", { name: "Labels" }));

        expect(onModeChange).toHaveBeenCalledWith("label");
        expect(screen.getByRole("dialog", { name: "Legend" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /SNARE/ })).toHaveAttribute("aria-pressed", "true");
    });

    it("says so while the chosen mode has no tag yet", () => {
        renderSheet({ tags: [] });

        expect(screen.getByText(EMPTY_CAPTION)).toBeInTheDocument();
        expect(screen.queryByRole("group", { name: "Painted tags" })).not.toBeInTheDocument();
    });

    it("reports the tag a person toggles", () => {
        const onToggle = vi.fn();
        renderSheet({ onToggle });

        fireEvent.click(screen.getByRole("button", { name: /PIANO/ }));

        expect(onToggle).toHaveBeenCalledWith("PIANO");
    });
});
