import type { ChangeEvent, ReactElement } from "react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { TrackerFormat } from "../api/modules";
import { ErrorNotice } from "../shared/ErrorNotice";
import { formatBytes } from "../shared/format";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";
import { Loading } from "../shared/Loading";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useModuleList } from "./useModuleList";

const PAGE_SIZE = 50;

export function ModuleListPage(): ReactElement {
    const [offset, setOffset] = useState(0);
    const [tracker, setTracker] = useState<TrackerFormat | null>(null);
    const state = useModuleList({ limit: PAGE_SIZE, offset, tracker });

    function handleTrackerChange(event: ChangeEvent<HTMLSelectElement>): void {
        const { value } = event.target;
        setTracker(value === "" ? null : (value as TrackerFormat));
        setOffset(0);
    }

    return (
        <section>
            <h1>Modules</h1>
            <label>
                Tracker
                <select value={tracker ?? ""} onChange={handleTrackerChange}>
                    <option value="">All</option>
                    <option value="xm">XM</option>
                    <option value="it">IT</option>
                </select>
            </label>
            {state.status === "loading" && <Loading />}
            {state.status === "error" && <ErrorNotice message={state.message} />}
            {state.status === "success" && (
                <>
                    <table>
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
                            {state.data.items.map((module) => (
                                <tr key={module.hash}>
                                    <td>
                                        <Link to={`/modules/${module.hash}`}>
                                            <OptionalLabel value={module.title} placeholder={UNTITLED_MODULE_LABEL} />
                                        </Link>
                                    </td>
                                    <td>{module.filename}</td>
                                    <td>{module.tracker}</td>
                                    <td>{module.sample_count}</td>
                                    <td>{formatBytes(module.file_size)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <nav aria-label="pagination">
                        <button
                            type="button"
                            disabled={offset === 0}
                            onClick={() => {
                                setOffset(Math.max(0, offset - PAGE_SIZE));
                            }}
                        >
                            Previous
                        </button>
                        <span>
                            {offset + 1}–{Math.min(offset + PAGE_SIZE, state.data.total)} of {state.data.total}
                        </span>
                        <button
                            type="button"
                            disabled={offset + PAGE_SIZE >= state.data.total}
                            onClick={() => {
                                setOffset(offset + PAGE_SIZE);
                            }}
                        >
                            Next
                        </button>
                    </nav>
                </>
            )}
        </section>
    );
}
