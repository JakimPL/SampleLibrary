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
import { ModuleRow } from "./ModuleRow";

const ROW_HEIGHT_PX = 28;
const OVERSCAN_ROWS = 12;
const INITIAL_VIEWPORT_HEIGHT_PX = 480;

const columnHelper = createColumnHelper<Module>();

const COLUMNS = [
    columnHelper.accessor((module) => (module.title.trim() === "" ? UNTITLED_MODULE_LABEL : module.title), {
        id: "title",
        header: "Title",
    }),
    columnHelper.accessor("filename", { header: "Filename" }),
    columnHelper.accessor("tracker", { header: "Tracker" }),
    columnHelper.accessor("sample_count", { header: "Samples" }),
    columnHelper.accessor("file_size", { header: "Size" }),
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
        estimateSize: () => ROW_HEIGHT_PX,
        overscan: OVERSCAN_ROWS,
        initialRect: { width: 0, height: INITIAL_VIEWPORT_HEIGHT_PX },
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
                    </select>
                </label>
                <span className="cell-muted mono">
                    {rows.length} / {modules.length}
                </span>
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
