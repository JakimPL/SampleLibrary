import type { ChangeEvent, ReactElement } from "react";

import type { Module, TrackerFormat } from "../api/modules";
import { ModuleRow } from "./ModuleRow";

interface ModulesTableProps {
    readonly modules: readonly Module[];
    readonly total: number;
    readonly offset: number;
    readonly limit: number;
    readonly tracker: TrackerFormat | null;
    readonly onOffsetChange: (offset: number) => void;
    readonly onTrackerChange: (tracker: TrackerFormat | null) => void;
}

export function ModulesTable({
    modules,
    total,
    offset,
    limit,
    tracker,
    onOffsetChange,
    onTrackerChange,
}: ModulesTableProps): ReactElement {
    function handleTrackerChange(event: ChangeEvent<HTMLSelectElement>): void {
        const { value } = event.target;
        onTrackerChange(value === "" ? null : (value as TrackerFormat));
    }

    return (
        <>
            <div className="panel-filter">
                <label>
                    Tracker
                    <select value={tracker ?? ""} onChange={handleTrackerChange}>
                        <option value="">All</option>
                        <option value="xm">XM</option>
                        <option value="it">IT</option>
                    </select>
                </label>
            </div>
            <table className="data">
                <thead>
                    <tr>
                        <th>Title</th>
                        <th>Filename</th>
                        <th>Tracker</th>
                        <th>Samples</th>
                        <th>Size</th>
                    </tr>
                </thead>
                <tbody>
                    {modules.map((module) => (
                        <ModuleRow key={module.hash} module={module} />
                    ))}
                </tbody>
            </table>
            <nav aria-label="pagination">
                <button
                    type="button"
                    disabled={offset === 0}
                    onClick={() => {
                        onOffsetChange(Math.max(0, offset - limit));
                    }}
                >
                    Previous
                </button>
                <span>
                    {offset + 1}–{Math.min(offset + limit, total)} of {total}
                </span>
                <button
                    type="button"
                    disabled={offset + limit >= total}
                    onClick={() => {
                        onOffsetChange(offset + limit);
                    }}
                >
                    Next
                </button>
            </nav>
        </>
    );
}
