import type { ReactElement } from "react";

import type { LibraryStats } from "../api/stats";
import { formatBytes } from "../shared/format";

interface StatsViewProps {
    readonly stats: LibraryStats;
}

export function StatsView({ stats }: StatsViewProps): ReactElement {
    return (
        <section>
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
            <h3>Modules by tracker</h3>
            <ul>
                {stats.modules_by_tracker.map((entry) => (
                    <li key={entry.tracker}>
                        {entry.tracker}: {entry.module_count}
                    </li>
                ))}
            </ul>
            <h3>Relations by type</h3>
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
