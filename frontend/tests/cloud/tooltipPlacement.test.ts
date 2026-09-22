import { describe, expect, it } from "vitest";

import { placeTooltip, samePlacement, TOOLTIP_GAP_PX } from "../../src/cloud/tooltipPlacement";

const TOOLTIP = { widthPx: 200, heightPx: 60 };
const CONTAINER = { widthPx: 600, heightPx: 400 };

describe("placeTooltip", () => {
    it("stands to the right of and above a point with room on both sides", () => {
        expect(placeTooltip(300, 200, TOOLTIP, CONTAINER)).toEqual({ left: false, below: false });
    });

    it("moves to the left of a point near the right edge", () => {
        expect(placeTooltip(CONTAINER.widthPx - TOOLTIP.widthPx, 200, TOOLTIP, CONTAINER)).toEqual({
            left: true,
            below: false,
        });
    });

    it("hangs below a point near the top edge", () => {
        expect(placeTooltip(300, TOOLTIP.heightPx, TOOLTIP, CONTAINER)).toEqual({ left: false, below: true });
    });

    it("turns both ways in the top right corner", () => {
        expect(placeTooltip(CONTAINER.widthPx - 1, 1, TOOLTIP, CONTAINER)).toEqual({ left: true, below: true });
    });

    it("keeps its side when the other side has no room either", () => {
        const wide = { widthPx: CONTAINER.widthPx, heightPx: CONTAINER.heightPx };

        expect(placeTooltip(CONTAINER.widthPx - 1, 1, wide, CONTAINER)).toEqual({ left: false, below: false });
    });

    it("counts the gap it keeps from the point", () => {
        const justFits = CONTAINER.widthPx - TOOLTIP.widthPx - TOOLTIP_GAP_PX;

        expect(placeTooltip(justFits, 200, TOOLTIP, CONTAINER).left).toBe(false);
        expect(placeTooltip(justFits + 1, 200, TOOLTIP, CONTAINER).left).toBe(true);
    });
});

describe("samePlacement", () => {
    it("reads two placements as one when both sides agree", () => {
        expect(samePlacement({ left: true, below: false }, { left: true, below: false })).toBe(true);
        expect(samePlacement({ left: true, below: false }, { left: true, below: true })).toBe(false);
    });
});
