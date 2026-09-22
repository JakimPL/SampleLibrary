/** How far the tooltip stands from the point it names, on either axis; the stylesheet's transforms carry the same value. */
export const TOOLTIP_GAP_PX = 14;

export interface TooltipPlacement {
    /** Whether the tooltip stands to the left of the point, its right edge at the point. */
    readonly left: boolean;
    /** Whether the tooltip hangs below the point. */
    readonly below: boolean;
}

export interface TooltipBox {
    readonly widthPx: number;
    readonly heightPx: number;
}

export const AT_RIGHT_ABOVE: TooltipPlacement = { left: false, below: false };

/**
 * Where a tooltip anchored at `x`, `y` fits inside its container: to the right of and above the
 * point by default, moved to the left where it would leave the right edge and the left has room,
 * and below the point where it would leave the top and the bottom has room.
 */
export function placeTooltip(x: number, y: number, tooltip: TooltipBox, container: TooltipBox): TooltipPlacement {
    const leavesRight = x + TOOLTIP_GAP_PX + tooltip.widthPx > container.widthPx;
    const fitsLeft = x - TOOLTIP_GAP_PX - tooltip.widthPx >= 0;
    const leavesTop = y - TOOLTIP_GAP_PX - tooltip.heightPx < 0;
    const fitsBelow = y + TOOLTIP_GAP_PX + tooltip.heightPx <= container.heightPx;
    return { left: leavesRight && fitsLeft, below: leavesTop && fitsBelow };
}

export function samePlacement(first: TooltipPlacement, second: TooltipPlacement): boolean {
    return first.left === second.left && first.below === second.below;
}
