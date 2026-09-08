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
import { RATING_VALUES } from "./rating";
import { SampleRow } from "./SampleRow";

const ROW_HEIGHT_PX = 44;
const OVERSCAN_ROWS = 12;
const INITIAL_VIEWPORT_HEIGHT_PX = 480;

// Calls onLoadMore once the virtualizer's rendered range comes within this many rows of the end
// of the currently loaded (and possibly filtered) list, so the next window arrives before the
// user actually scrolls past the last loaded sample.
const LOAD_MORE_TRIGGER_DISTANCE = 20;

const columnHelper = createColumnHelper<SampleSummary>();

const COLUMNS = [
    columnHelper.display({ id: "waveform", header: "Waveform" }),
    columnHelper.accessor(
        (sample) => (sample.display_name.trim() === "" ? UNNAMED_SAMPLE_LABEL : sample.display_name),
        {
            id: "name",
            header: "Name",
        },
    ),
    columnHelper.display({ id: "category", header: "Category" }),
    columnHelper.display({ id: "verdict", header: "Rating" }),
    columnHelper.accessor("size_bytes", { header: "Size" }),
    columnHelper.accessor("occurrence_count", { header: "Occurrences" }),
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
        estimateSize: () => ROW_HEIGHT_PX,
        overscan: OVERSCAN_ROWS,
        initialRect: { width: 0, height: INITIAL_VIEWPORT_HEIGHT_PX },
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
                    aria-label="Minimum rating"
                    value={selection.minimumRating === null ? "" : String(selection.minimumRating)}
                    onChange={(event) => {
                        onSelectionChange({
                            ...selection,
                            minimumRating: event.target.value === "" ? null : Number(event.target.value),
                        });
                    }}
                >
                    <option value="">Any rating</option>
                    {RATING_VALUES.map((value) => (
                        <option key={value} value={value}>
                            {value}+
                        </option>
                    ))}
                </select>
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
                <span className="cell-muted mono">
                    {samples.length} of {total} loaded
                    {isLoadingMore && hasMore ? " · loading…" : ""}
                </span>
                {loadMoreError !== null && <span className="error-notice">{loadMoreError}</span>}
            </div>
            <div className="panel-body" ref={scrollElementRef}>
                <table className="data">
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
                            return row ? <SampleRow key={row.original.hash} sample={row.original} /> : null;
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
