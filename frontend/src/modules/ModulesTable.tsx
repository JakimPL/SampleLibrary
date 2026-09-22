import {
    flexRender,
    getCoreRowModel,
    getFilteredRowModel,
    getSortedRowModel,
    type SortingState,
    useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ChangeEvent, ReactElement } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Module, TrackerFormat } from "../api/modules";
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
import { MODULE_COLUMN_SPEC, MODULE_COLUMNS } from "./moduleColumns";
import { ModuleRow } from "./ModuleRow";

interface ModulesTableProps {
    readonly modules: readonly Module[];
}

/**
 * The modules listing: a virtualized table over the whole catalog, whose columns yield one by one
 * as its panel narrows so the title always keeps its room.
 */
export function ModulesTable({ modules }: ModulesTableProps): ReactElement {
    const [tracker, setTracker] = useState<TrackerFormat | null>(null);
    const [globalFilter, setGlobalFilter] = useState("");
    const [sorting, setSorting] = useState<SortingState>([]);
    const scrollElementRef = useRef<HTMLDivElement | null>(null);
    const { input } = useLayoutMode();
    const width = useContainerWidth(scrollElementRef);
    const visibleColumns = useMemo(() => fitColumns(MODULE_COLUMN_SPEC, width ?? Number.POSITIVE_INFINITY), [width]);
    const columnVisibility = useMemo(
        () => Object.fromEntries(MODULE_COLUMN_SPEC.map((column) => [column.id, visibleColumns.has(column.id)])),
        [visibleColumns],
    );

    const filteredByTracker = useMemo(
        () => Array.from(tracker === null ? modules : modules.filter((module) => module.tracker === tracker)),
        [modules, tracker],
    );

    const table = useReactTable({
        data: filteredByTracker,
        columns: MODULE_COLUMNS,
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

    function handleTrackerChange(event: ChangeEvent<HTMLSelectElement>): void {
        const { value } = event.target;
        setTracker(value === "" ? null : (value as TrackerFormat));
    }

    return (
        <div className="panel-stack">
            <PanelToolbar
                primary={
                    <input
                        type="text"
                        placeholder="Filter modules…"
                        value={globalFilter}
                        onChange={(event) => {
                            setGlobalFilter(event.target.value);
                        }}
                    />
                }
                secondary={
                    <label>
                        Tracker
                        <select value={tracker ?? ""} onChange={handleTrackerChange}>
                            <option value="">All</option>
                            <option value="xm">XM</option>
                            <option value="it">IT</option>
                            <option value="mod">MOD</option>
                            <option value="s3m">S3M</option>
                        </select>
                    </label>
                }
                status={
                    <span className="cell-muted mono">
                        {rows.length} of {modules.length} shown
                    </span>
                }
            />
            <div className="panel-body" ref={scrollElementRef}>
                <table className="data">
                    <TableColgroup table={table} spec={MODULE_COLUMN_SPEC} />
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
                                <ModuleRow
                                    key={row.original.hash}
                                    module={row.original}
                                    visibleColumns={visibleColumns}
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
