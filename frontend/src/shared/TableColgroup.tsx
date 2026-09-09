import type { RowData, Table } from "@tanstack/react-table";
import type { ReactElement } from "react";

declare module "@tanstack/react-table" {
    // The table library's own extension point for per-column facts of a caller's own. Both type
    // parameters belong to its declaration and are named here to match it.
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    interface ColumnMeta<TData extends RowData, TValue> {
        /** Marks the one column that takes whatever width the sized columns leave over. */
        readonly flexible?: boolean;
    }
}

interface TableColgroupProps<TData> {
    readonly table: Table<TData>;
}

/**
 * The column widths a `table-layout: fixed` table lays itself out by, taken from each column's own
 * `size`. The column marked `meta.flexible` is left unsized, so it takes the remaining width.
 *
 * A virtualized table renders only the rows on screen, so an automatic layout would measure a fresh
 * set of cells at every scroll position and hand each column a different width as a person scrolls.
 * Declaring the widths up front is what holds a column still while the rows underneath it change.
 */
export function TableColgroup<TData>({ table }: TableColgroupProps<TData>): ReactElement {
    return (
        <colgroup>
            {table.getAllLeafColumns().map((column) => (
                <col
                    key={column.id}
                    {...(column.columnDef.meta?.flexible === true ? {} : { style: { width: column.getSize() } })}
                />
            ))}
        </colgroup>
    );
}
