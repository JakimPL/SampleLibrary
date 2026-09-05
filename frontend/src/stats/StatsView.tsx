import type { ReactElement } from "react";

import type { LibraryStats } from "../api/stats";
import { formatBytes } from "../shared/format";

interface StatsViewProps {
    readonly stats: LibraryStats;
}

export function StatsView({ stats }: StatsViewProps): ReactElement {
    return (
        <section className="stats-grid">
            <div className="stat-tile">
                <div className="big mono">{stats.module_count}</div>
                <div className="label">Modules</div>
            </div>
            <div className="stat-tile">
                <div className="big mono">{stats.sample_count}</div>
                <div className="label">Samples</div>
            </div>
            <div className="stat-tile">
                <div className="big mono">{stats.sample_properties_count}</div>
                <div className="label">Sample properties</div>
            </div>
            <div className="stat-tile">
                <div className="big mono">{formatBytes(stats.total_stored_bytes)}</div>
                <div className="label">Stored audio</div>
            </div>
            <div className="chart-card">
                <h3>Modules by tracker</h3>
                <ul>
                    {stats.modules_by_tracker.map((entry) => (
                        <li key={entry.tracker}>
                            {entry.tracker}: {entry.module_count}
                        </li>
                    ))}
                </ul>
            </div>
            <div className="chart-card">
                <h3>Relations by type</h3>
                <ul>
                    {stats.relations_by_type.map((entry) => (
                        <li key={entry.relation_type}>
                            {entry.relation_type}: {entry.relation_count}
                        </li>
                    ))}
                </ul>
            </div>
        </section>
    );
}
