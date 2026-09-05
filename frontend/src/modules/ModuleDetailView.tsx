import type { ReactElement } from "react";

import type { ModuleDetail } from "../api/modules";
import { formatBytes } from "../shared/format";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { ModuleSampleRow } from "./ModuleSampleRow";

interface ModuleDetailViewProps {
    readonly module: ModuleDetail;
}

export function ModuleDetailView({ module }: ModuleDetailViewProps): ReactElement {
    return (
        <section className="detail-scroll">
            <h2>
                <OptionalLabel value={module.title} placeholder={UNTITLED_MODULE_LABEL} />
            </h2>
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
                            <th>Waveform</th>
                            <th>Name</th>
                            <th>Instrument</th>
                            <th>Slot</th>
                            <th>Rate</th>
                            <th>Volume</th>
                            <th>Panning</th>
                            <th>Loop</th>
                            <th>Size</th>
                            <th>Depth</th>
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
