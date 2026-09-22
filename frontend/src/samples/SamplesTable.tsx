import {
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
import { useContainerWidth } from "../layout/useContainerWidth";
import { useLayoutMode } from "../layout/useLayoutMode";
import { fitColumns } from "../shared/columnFit";
import { PanelToolbar } from "../shared/panel/PanelToolbar";
import { TableColgroup } from "../shared/TableColgroup";
import {
    TABLE_INITIAL_VIEWPORT_HEIGHT_PX,
    TABLE_OVERSCAN_ROWS,
    TABLE_ROW_HEIGHT_BY_INPUT,
} from "../shared/tableMetrics";
import { SAMPLE_COLUMNS, sampleColumnSpec } from "./sampleColumns";
import { SampleRow } from "./SampleRow";

const LOAD_MORE_TRIGGER_DISTANCE = 20;

interface SamplesTableProps {
    readonly samples: readonly SampleSummary[];
    readonly loadedCount: number;
    readonly groupCount: number;
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

/**
 * The samples listing: a virtualized table whose columns yield one by one as its panel narrows,
 * the counts first and the name last, so the same listing reads in a wide workspace column and on
 * a phone. Under touch the rows grow to a finger's height and the verdict column keeps the heart
 * alone, the stars being a tap away elsewhere.
 */
export function SamplesTable({
    samples,
    loadedCount,
    groupCount,
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
    const { input } = useLayoutMode();
    const spec = useMemo(() => sampleColumnSpec(input), [input]);
    const width = useContainerWidth(scrollElementRef);
    const visibleColumns = useMemo(() => fitColumns(spec, width ?? Number.POSITIVE_INFINITY), [spec, width]);
    const columnVisibility = useMemo(
        () => Object.fromEntries(spec.map((column) => [column.id, visibleColumns.has(column.id)])),
        [spec, visibleColumns],
    );

    const data = useMemo(() => Array.from(samples), [samples]);

    const table = useReactTable({
        data,
        columns: SAMPLE_COLUMNS,
        state: { sorting, globalFilter, columnVisibility },
        onSortingChange: setSorting,
        onGlobalFilterChange: setGlobalFilter,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
    });
    const rows = table.getRowModel().rows;
    const visibleColumnCount = table.getVisibleLeafColumns().length;

    const rowHeight = TABLE_ROW_HEIGHT_BY_INPUT[input];
    const virtualizer = useVirtualizer({
        count: rows.length,
        getScrollElement: () => scrollElementRef.current,
        estimateSize: () => rowHeight,
        overscan: TABLE_OVERSCAN_ROWS,
        initialRect: { width: 0, height: TABLE_INITIAL_VIEWPORT_HEIGHT_PX },
    });
    useEffect(() => {
        virtualizer.measure();
    }, [virtualizer, rowHeight]);
    const virtualRows = virtualizer.getVirtualItems();
    const lastVirtualRow = virtualRows[virtualRows.length - 1];
    const paddingTop = virtualRows[0]?.start ?? 0;
    const paddingBottom = lastVirtualRow ? virtualizer.getTotalSize() - lastVirtualRow.end : 0;
    const lastVirtualIndex = lastVirtualRow?.index ?? -1;

    // A filter or a column sort narrows or reorders only the rows already held, so loading more under
    // one would page through the catalog without ever reaching what the person is looking for; a
    // button asks for the next window instead. Otherwise the next window is asked for once per row count.
    const isNarrowed = globalFilter !== "" || sorting.length > 0;
    const requestedAtRef = useRef<number | null>(null);
    useEffect(() => {
        if (
            !isNarrowed &&
            hasMore &&
            lastVirtualIndex >= rows.length - LOAD_MORE_TRIGGER_DISTANCE &&
            requestedAtRef.current !== loadedCount
        ) {
            requestedAtRef.current = loadedCount;
            onLoadMore();
        }
    }, [isNarrowed, hasMore, lastVirtualIndex, rows.length, loadedCount, onLoadMore]);

    return (
        <div className="panel-stack">
            <PanelToolbar
                primary={
                    <input
                        type="text"
                        placeholder="Filter samples…"
                        value={globalFilter}
                        onChange={(event) => {
                            setGlobalFilter(event.target.value);
                        }}
                    />
                }
                secondary={
                    <>
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
                    </>
                }
                status={
                    <>
                        <span className="cell-muted mono">
                            {loadedCount} of {total} loaded
                            {groupByEquivalence ? ` · ${String(groupCount)} groups` : ""}
                            {isLoadingMore && hasMore ? " · loading…" : ""}
                        </span>
                        {isNarrowed && hasMore && (
                            <button type="button" onClick={onLoadMore} disabled={isLoadingMore}>
                                Load more
                            </button>
                        )}
                        {loadMoreError !== null && <span className="error-notice">{loadMoreError}</span>}
                    </>
                }
            />
            <div className="panel-body" ref={scrollElementRef}>
                <table className="data">
                    <TableColgroup table={table} spec={spec} />
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
                                <td colSpan={visibleColumnCount} />
                            </tr>
                        )}
                        {virtualRows.map((virtualRow) => {
                            const row = rows[virtualRow.index];
                            return row ? (
                                <SampleRow
                                    key={row.original.hash}
                                    sample={row.original}
                                    groupByEquivalence={groupByEquivalence}
                                    visibleColumns={visibleColumns}
                                    input={input}
                                />
                            ) : null;
                        })}
                        {paddingBottom > 0 && (
                            <tr aria-hidden="true" style={{ height: paddingBottom }}>
                                <td colSpan={visibleColumnCount} />
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
