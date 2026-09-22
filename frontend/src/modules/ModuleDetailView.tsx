import type { ReactElement } from "react";

import type { ModuleDetail } from "../api/modules";
import { DetailHeader } from "../shared/DetailHeader";
import { formatBytes } from "../shared/format";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";
import { MODULE_SAMPLE_COLUMN_LABELS, ModuleSampleRow } from "./ModuleSampleRow";

interface ModuleDetailViewProps {
    readonly module: ModuleDetail;
}

export function ModuleDetailView({ module }: ModuleDetailViewProps): ReactElement {
    return (
        <section className="detail-scroll">
            <DetailHeader name={module.title} placeholder={UNTITLED_MODULE_LABEL} hash={module.hash} />
            <dl className="kv">
                <dt>Filename</dt>
                <dd>{module.filename}</dd>
                <dt>Tracker</dt>
                <dd>
                    <span className={`badge badge-${module.tracker}`}>{module.tracker}</span>
                </dd>
                <dt>Channels</dt>
                <dd className="mono">{module.channel_count}</dd>
                <dt>Patterns</dt>
                <dd className="mono">{module.pattern_count}</dd>
                <dt>Instruments</dt>
                <dd className="mono">{module.instrument_count}</dd>
                <dt>Samples</dt>
                <dd className="mono">{module.sample_count}</dd>
                <dt>File Size</dt>
                <dd className="mono">{formatBytes(module.file_size)}</dd>
                <dt>Ingested At</dt>
                <dd>{new Date(module.ingested_at).toLocaleString()}</dd>
            </dl>
            <div className="detail-section">
                <h3>Samples</h3>
                <table className="mini">
                    <thead>
                        <tr>
                            {Object.values(MODULE_SAMPLE_COLUMN_LABELS).map((label) => (
                                <th key={label}>{label}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {module.occurrences.map((occurrence) => (
                            <ModuleSampleRow
                                key={`${String(occurrence.properties.occurrence.instrument_index)}-${String(occurrence.properties.occurrence.sample_slot)}`}
                                occurrence={occurrence}
                            />
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
