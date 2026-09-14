import type { GridStyle } from "./cloudRenderSettings";
import { gridLinesBetween, type GridRank, gridStep } from "./gridSpacing";
import { devicePixels } from "./markerGeometry";
import { toScreen, type ViewTransform, visibleBounds } from "./viewTransform";

/** The part of a 2D canvas context the grid paints through. */
export interface GridCanvas {
    strokeStyle: CanvasRenderingContext2D["strokeStyle"];
    lineWidth: number;
    beginPath: () => void;
    moveTo: (x: number, y: number) => void;
    lineTo: (x: number, y: number) => void;
    stroke: () => void;
}

/** A canvas's own size in device pixels. */
export interface DeviceSize {
    readonly width: number;
    readonly height: number;
}

const RANKS: readonly GridRank[] = ["row", "beat", "measure"];
const TRANSPARENT = "transparent";
const HALF = 0.5;
const PARITY = 2;
const VERTICAL_AXES = "vertical";
const NO_MARGIN = 0;

function rankColor(grid: GridStyle, rank: GridRank): string {
    switch (rank) {
        case "row":
            return grid.rowColor;
        case "beat":
            return grid.beatColor;
        case "measure":
            return grid.measureColor;
    }
}

/** Where a line of `lineWidth` device pixels runs so it covers whole pixels: through a pixel's center when odd, along a boundary when even. */
function crispCoordinate(devicePosition: number, lineWidth: number): number {
    return lineWidth % PARITY === 1 ? Math.floor(devicePosition) + HALF : Math.round(devicePosition);
}

/**
 * Paints `grid` as `transform` shows the data onto a canvas of `size` device pixels: vertical lines
 * at every step along x and, when the grid takes both axes, horizontal ones along y, each rank
 * stroked as one path in its own color, rows first and measures last so the stronger lines lie on
 * top. The horizontal line through the data's zero comes last of all. Lines follow the camera, so
 * the grid pans and zooms with the points it lies under.
 */
export function paintGrid(context: GridCanvas, transform: ViewTransform, grid: GridStyle, size: DeviceSize): void {
    if (grid.lineWidthPx <= 0) {
        return;
    }
    const lineWidth = devicePixels(grid.lineWidthPx, transform.devicePixelRatio);
    const scaleX = size.width / transform.widthPx;
    const scaleY = size.height / transform.heightPx;
    const bounds = visibleBounds(transform, NO_MARGIN);
    const vertical = gridLinesBetween(
        bounds.minimumX,
        bounds.maximumX,
        gridStep(Math.abs(transform.xx), grid.spacingPx),
    );
    const horizontal =
        grid.axes === VERTICAL_AXES
            ? []
            : gridLinesBetween(bounds.minimumY, bounds.maximumY, gridStep(Math.abs(transform.yy), grid.spacingPx));
    context.lineWidth = lineWidth;
    for (const rank of RANKS) {
        const color = rankColor(grid, rank);
        if (color === TRANSPARENT) {
            continue;
        }
        context.strokeStyle = color;
        context.beginPath();
        for (const line of vertical.filter((candidate) => candidate.rank === rank)) {
            const x = crispCoordinate(toScreen(transform, line.value, 0)[0] * scaleX, lineWidth);
            context.moveTo(x, 0);
            context.lineTo(x, size.height);
        }
        for (const line of horizontal.filter((candidate) => candidate.rank === rank)) {
            const y = crispCoordinate(toScreen(transform, 0, line.value)[1] * scaleY, lineWidth);
            context.moveTo(0, y);
            context.lineTo(size.width, y);
        }
        context.stroke();
    }
    if (grid.centerColor !== TRANSPARENT) {
        const y = crispCoordinate(toScreen(transform, 0, 0)[1] * scaleY, lineWidth);
        context.strokeStyle = grid.centerColor;
        context.beginPath();
        context.moveTo(0, y);
        context.lineTo(size.width, y);
        context.stroke();
    }
}
