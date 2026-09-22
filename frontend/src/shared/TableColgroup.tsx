import type { Table } from "@tanstack/react-table";
import type { ReactElement } from "react";

import type { FittableColumn } from "./columnFit";

interface TableColgroupProps<TData> {
    readonly table: Table<TData>;
    readonly spec: readonly FittableColumn[];
}

/**
 * The column widths a `table-layout: fixed` table lays itself out by, one `<col>` per column on
 * show, each sized as `spec` asks; the flexible column is left unsized, so it takes the remaining
 * width.
 *
 * A virtualized table renders only the rows on screen, so an automatic layout would measure a fresh
 * set of cells at every scroll position and hand each column a different width as a person scrolls.
 * Declaring the widths up front is what holds a column still while the rows underneath it change.
 */
export function TableColgroup<TData>({ table, spec }: TableColgroupProps<TData>): ReactElement {
    const widthById = new Map(spec.map((column) => [column.id, column.widthPx]));
    return (
        <colgroup>
            {table.getVisibleLeafColumns().map((column) => {
                const width = widthById.get(column.id) ?? null;
                return <col key={column.id} {...(width === null ? {} : { style: { width } })} />;
            })}
        </colgroup>
    );
}
