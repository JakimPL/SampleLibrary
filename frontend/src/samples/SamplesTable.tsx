import {
    createColumnHelper,
    flexRender,
    getCoreRowModel,
    getFilteredRowModel,
    getSortedRowModel,
    type SortingState,
    useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ReactElement } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { SampleSelection, SampleSummary } from "../api/samples";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { TableColgroup } from "../shared/TableColgroup";
import { TABLE_INITIAL_VIEWPORT_HEIGHT_PX, TABLE_OVERSCAN_ROWS, TABLE_ROW_HEIGHT_PX } from "../shared/tableMetrics";
import { SampleRow } from "./SampleRow";

// Calls onLoadMore once the virtualizer's rendered range comes within this many rows of the end
// of the currently loaded (and possibly filtered) list, so the next window arrives before the
// user actually scrolls past the last loaded sample.
const LOAD_MORE_TRIGGER_DISTANCE = 20;

const columnHelper = createColumnHelper<SampleSummary>();

// Every column but the name declares its own width, so the name takes whatever the others leave
// over. Each width holds that column's own widest reading -- five stars and a heart, a formatted
// byte count, a header word -- since these are read whole or not at all, while a name is the one
// thing a listing can trail off and still say something with.
const COLUMNS = [
    columnHelper.display({ id: "waveform", header: "Waveform", size: 76 }),
    columnHelper.accessor(
        (sample) => (sample.display_name.trim() === "" ? UNNAMED_SAMPLE_LABEL : sample.display_name),
        {
            id: "name",
            header: "Name",
            meta: { flexible: true },
        },
    ),
    columnHelper.display({ id: "category", header: "Category", size: 96 }),
    columnHelper.display({ id: "verdict", header: "Rating", size: 110 }),
    columnHelper.accessor("size_bytes", { header: "Size", size: 80 }),
    columnHelper.accessor("occurrence_count", { header: "Occurrences", size: 84 }),
];

interface SamplesTableProps {
    readonly samples: readonly SampleSummary[];
    readonly total: number;
    readonly hasMore: boolean;
    readonly isLoadingMore: boolean;
    readonly onLoadMore: () => void;
    readonly loadMoreError: string | null;
    readonly groupByEquivalence: boolean;
    readonly onGroupByEquivalenceChange: (groupByEquivalence: boolean) => void;
    readonly selection: SampleSelection;
    readonly onSelectionChange: (selection: SampleSelection) => void;
}

export function SamplesTable({
    samples,
    total,
    hasMore,
    isLoadingMore,
    onLoadMore,
    loadMoreError,
    groupByEquivalence,
    onGroupByEquivalenceChange,
    selection,
    onSelectionChange,
}: SamplesTableProps): ReactElement {
    const [globalFilter, setGlobalFilter] = useState("");
    const [sorting, setSorting] = useState<SortingState>([]);
    const scrollElementRef = useRef<HTMLDivElement | null>(null);

    const data = useMemo(() => Array.from(samples), [samples]);

    const table = useReactTable({
        data,
        columns: COLUMNS,
        state: { sorting, globalFilter },
        onSortingChange: setSorting,
        onGlobalFilterChange: setGlobalFilter,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
    });
    const rows = table.getRowModel().rows;

    const virtualizer = useVirtualizer({
        count: rows.length,
        getScrollElement: () => scrollElementRef.current,
        estimateSize: () => TABLE_ROW_HEIGHT_PX,
        overscan: TABLE_OVERSCAN_ROWS,
        initialRect: { width: 0, height: TABLE_INITIAL_VIEWPORT_HEIGHT_PX },
    });
    const virtualRows = virtualizer.getVirtualItems();
    const lastVirtualRow = virtualRows[virtualRows.length - 1];
    const paddingTop = virtualRows[0]?.start ?? 0;
    const paddingBottom = lastVirtualRow ? virtualizer.getTotalSize() - lastVirtualRow.end : 0;
    const lastVirtualIndex = lastVirtualRow?.index ?? -1;

    useEffect(() => {
        if (hasMore && lastVirtualIndex >= rows.length - LOAD_MORE_TRIGGER_DISTANCE) {
            onLoadMore();
        }
    }, [hasMore, lastVirtualIndex, rows.length, onLoadMore]);

    return (
        <div className="panel-stack">
            <div className="panel-status">
                <span className="cell-muted mono">
                    {samples.length} of {total} loaded
                    {isLoadingMore && hasMore ? " · loading…" : ""}
                </span>
                {loadMoreError !== null && <span className="error-notice">{loadMoreError}</span>}
            </div>
            <div className="panel-filter">
                <input
                    type="text"
                    placeholder="Filter samples…"
                    value={globalFilter}
                    onChange={(event) => {
                        setGlobalFilter(event.target.value);
                    }}
                />
                <label>
                    <input
                        type="checkbox"
                        checked={groupByEquivalence}
                        onChange={(event) => {
                            onGroupByEquivalenceChange(event.target.checked);
                        }}
                    />
                    Group similar
                </label>
                <button
                    type="button"
                    aria-pressed={selection.favoritesOnly}
                    onClick={() => {
                        onSelectionChange({ ...selection, favoritesOnly: !selection.favoritesOnly });
                    }}
                >
                    Favorites
                </button>
                <select
                    aria-label="Order"
                    value={selection.sort}
                    onChange={(event) => {
                        onSelectionChange({
                            ...selection,
                            sort: event.target.value === "rating" ? "rating" : "occurrences",
                        });
                    }}
                >
                    <option value="occurrences">Most used</option>
                    <option value="rating">Best rated</option>
                </select>
            </div>
            <div className="panel-body" ref={scrollElementRef}>
                <table className="data">
                    <TableColgroup table={table} />
                    <thead>
                        {table.getHeaderGroups().map((headerGroup) => (
                            <tr key={headerGroup.id}>
                                {headerGroup.headers.map((header) => {
                                    const sortDirection = header.column.getIsSorted();
                                    return (
                                        <th
                                            key={header.id}
                                            onClick={header.column.getToggleSortingHandler()}
                                            className={sortDirection ? "sorted" : undefined}
                                            aria-sort={
                                                sortDirection === "asc"
                                                    ? "ascending"
                                                    : sortDirection === "desc"
                                                      ? "descending"
                                                      : undefined
                                            }
                                        >
                                            {flexRender(header.column.columnDef.header, header.getContext())}
                                            {sortDirection === "asc" && <span className="arrow">▲</span>}
                                            {sortDirection === "desc" && <span className="arrow">▼</span>}
                                        </th>
                                    );
                                })}
                            </tr>
                        ))}
                    </thead>
                    <tbody>
                        {paddingTop > 0 && (
                            <tr aria-hidden="true" style={{ height: paddingTop }}>
                                <td colSpan={COLUMNS.length} />
                            </tr>
                        )}
                        {virtualRows.map((virtualRow) => {
                            const row = rows[virtualRow.index];
                            return row ? (
                                <SampleRow
                                    key={row.original.hash}
                                    sample={row.original}
                                    groupByEquivalence={groupByEquivalence}
                                />
                            ) : null;
                        })}
                        {paddingBottom > 0 && (
                            <tr aria-hidden="true" style={{ height: paddingBottom }}>
                                <td colSpan={COLUMNS.length} />
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
