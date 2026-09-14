/** How strongly a grid line reads: every line a row, every fourth a beat, every sixteenth a measure. */
export type GridRank = "row" | "beat" | "measure";

/** One grid line: where it stands along its axis in data units, and how strongly it reads. */
export interface GridLine {
    readonly value: number;
    readonly rank: GridRank;
}

const ROWS_PER_BEAT = 4;
const ROWS_PER_MEASURE = 16;
const OCTAVE = 2;

function positiveModulo(value: number, divisor: number): number {
    return ((value % divisor) + divisor) % divisor;
}

/**
 * The data-space step between grid lines under a zoom of `pixelsPerUnit`: the smallest power of two
 * that keeps lines at least `targetSpacingPx` apart. Powers of two nest -- every line of a coarser
 * grid stays a line of the finer one -- so zooming halves or doubles the grid in place, the way a
 * tracker's rows nest into beats and measures.
 */
export function gridStep(pixelsPerUnit: number, targetSpacingPx: number): number {
    return OCTAVE ** Math.ceil(Math.log2(targetSpacingPx / Math.max(Number.EPSILON, pixelsPerUnit)));
}

/** Every grid line from `minimum` to `maximum` at `step`, each ranked by its place in the four- and sixteen-row rhythm. */
export function gridLinesBetween(minimum: number, maximum: number, step: number): GridLine[] {
    const lines: GridLine[] = [];
    for (let index = Math.ceil(minimum / step); index * step <= maximum; index += 1) {
        const rank: GridRank =
            positiveModulo(index, ROWS_PER_MEASURE) === 0
                ? "measure"
                : positiveModulo(index, ROWS_PER_BEAT) === 0
                  ? "beat"
                  : "row";
        lines.push({ value: index * step, rank });
    }
    return lines;
}
