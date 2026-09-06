import type { ReactElement } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { LibraryStats } from "../api/stats";
import { formatBytes } from "../shared/format";

const CHART_HEIGHT_PX = 200;

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
                <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
                    <BarChart data={[...stats.modules_by_tracker]}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="tracker" stroke="var(--text-muted)" />
                        <YAxis allowDecimals={false} stroke="var(--text-muted)" />
                        <Tooltip />
                        <Bar dataKey="module_count" name="Modules" fill="var(--accent)" />
                    </BarChart>
                </ResponsiveContainer>
            </div>
            <div className="chart-card">
                <h3>Relations by type</h3>
                <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
                    <BarChart data={[...stats.relations_by_type]}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="relation_type" stroke="var(--text-muted)" />
                        <YAxis allowDecimals={false} stroke="var(--text-muted)" />
                        <Tooltip />
                        <Bar dataKey="relation_count" name="Relations" fill="var(--good)" />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </section>
    );
}
