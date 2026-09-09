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
import type { ChangeEvent, ReactElement } from "react";
import { useMemo, useRef, useState } from "react";

import type { Module, TrackerFormat } from "../api/modules";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";
import { TableColgroup } from "../shared/TableColgroup";
import { TABLE_INITIAL_VIEWPORT_HEIGHT_PX, TABLE_OVERSCAN_ROWS, TABLE_ROW_HEIGHT_PX } from "../shared/tableMetrics";
import { ModuleRow } from "./ModuleRow";

const columnHelper = createColumnHelper<Module>();

// The title takes whatever the sized columns leave over, the way a samples listing's name does.
const COLUMNS = [
    columnHelper.accessor((module) => (module.title.trim() === "" ? UNTITLED_MODULE_LABEL : module.title), {
        id: "title",
        header: "Title",
        meta: { flexible: true },
    }),
    columnHelper.accessor("filename", { header: "Filename", size: 220 }),
    columnHelper.accessor("tracker", { header: "Tracker", size: 72 }),
    columnHelper.accessor("sample_count", { header: "Samples", size: 72 }),
    columnHelper.accessor("file_size", { header: "Size", size: 72 }),
];

interface ModulesTableProps {
    readonly modules: readonly Module[];
}

export function ModulesTable({ modules }: ModulesTableProps): ReactElement {
    const [tracker, setTracker] = useState<TrackerFormat | null>(null);
    const [globalFilter, setGlobalFilter] = useState("");
    const [sorting, setSorting] = useState<SortingState>([]);
    const scrollElementRef = useRef<HTMLDivElement | null>(null);

    const filteredByTracker = useMemo(
        () => Array.from(tracker === null ? modules : modules.filter((module) => module.tracker === tracker)),
        [modules, tracker],
    );

    const table = useReactTable({
        data: filteredByTracker,
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

    function handleTrackerChange(event: ChangeEvent<HTMLSelectElement>): void {
        const { value } = event.target;
        setTracker(value === "" ? null : (value as TrackerFormat));
    }

    return (
        <div className="panel-stack">
            <div className="panel-filter">
                <input
                    type="text"
                    placeholder="Filter modules…"
                    value={globalFilter}
                    onChange={(event) => {
                        setGlobalFilter(event.target.value);
                    }}
                />
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
                <span className="cell-muted mono">
                    {rows.length} / {modules.length}
                </span>
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
                            return row ? <ModuleRow key={row.original.hash} module={row.original} /> : null;
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
