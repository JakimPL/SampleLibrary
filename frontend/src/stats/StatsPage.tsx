import type { ReactElement } from "react";

import { getStats } from "../api/stats";
import { ErrorNotice } from "../shared/ErrorNotice";
import { formatBytes } from "../shared/format";
import { Loading } from "../shared/Loading";
import { useFetch } from "../shared/useFetch";

const NO_DEPENDENCIES: readonly unknown[] = [];

export function StatsPage(): ReactElement {
    const state = useFetch(getStats, NO_DEPENDENCIES);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const stats = state.data;
    return (
        <section>
            <h1>Library stats</h1>
            <dl>
                <dt>Modules</dt>
                <dd>{stats.module_count}</dd>
                <dt>Samples</dt>
                <dd>{stats.sample_count}</dd>
                <dt>Sample properties</dt>
                <dd>{stats.sample_properties_count}</dd>
                <dt>Stored audio</dt>
                <dd>{formatBytes(stats.total_stored_bytes)}</dd>
            </dl>
            <h2>Modules by tracker</h2>
            <ul>
                {stats.modules_by_tracker.map((entry) => (
                    <li key={entry.tracker}>
                        {entry.tracker}: {entry.module_count}
                    </li>
                ))}
            </ul>
            <h2>Relations by type</h2>
            <ul>
                {stats.relations_by_type.map((entry) => (
                    <li key={entry.relation_type}>
                        {entry.relation_type}: {entry.relation_count}
                    </li>
                ))}
            </ul>
        </section>
    );
}
