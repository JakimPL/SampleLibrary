export interface FittableColumn<Id extends string = string> {
    readonly id: Id;
    /** The width the column asks for, or `null` for the one column that takes what the others leave. */
    readonly widthPx: number | null;
    /** The order the column leaves in as the width shrinks, from 1, or `null` for a column that stays. */
    readonly dropOrder: number | null;
}

/** The least the flexible column is given before another column has to leave. */
export const FLEXIBLE_COLUMN_MINIMUM_PX = 100;

function widthOf(column: FittableColumn): number {
    return column.widthPx ?? FLEXIBLE_COLUMN_MINIMUM_PX;
}

function leavesBefore(first: FittableColumn, second: FittableColumn): number {
    return (first.dropOrder ?? Number.POSITIVE_INFINITY) - (second.dropOrder ?? Number.POSITIVE_INFINITY);
}

/**
 * The columns that fit side by side in `availableWidthPx`: every column that stays, and as many of
 * the others as the width holds, the ones marked to leave first going first. A width still short of
 * the columns that stay keeps them all, and the table scrolls sideways for the difference.
 */
export function fitColumns<Id extends string>(
    columns: readonly FittableColumn<Id>[],
    availableWidthPx: number,
): ReadonlySet<Id> {
    const kept = new Set(columns.map((column) => column.id));
    let total = columns.reduce((sum, column) => sum + widthOf(column), 0);
    for (const column of [...columns].filter((candidate) => candidate.dropOrder !== null).sort(leavesBefore)) {
        if (total <= availableWidthPx) {
            break;
        }
        kept.delete(column.id);
        total -= widthOf(column);
    }
    return kept;
}
