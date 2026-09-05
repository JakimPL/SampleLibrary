import type { ReactElement } from "react";

import type { SampleDetail, SampleRelation, WaveformPeak } from "../api/samples";
import { formatBytes, formatDuration } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { CATEGORY_PLACEHOLDER } from "./category";
import { SampleOccurrenceRow } from "./SampleOccurrenceRow";
import { SampleRelationRow } from "./SampleRelationRow";
import { Waveform } from "./Waveform";

interface SampleDetailViewProps {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
    readonly waveform: readonly WaveformPeak[];
}

export function SampleDetailView({ sample, relations, waveform }: SampleDetailViewProps): ReactElement {
    return (
        <section>
            <h2>
                <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
            </h2>
            <p className="hash">{sample.hash}</p>
            <dl>
                <dt>Category</dt>
                <dd>{CATEGORY_PLACEHOLDER}</dd>
                <dt>Size</dt>
                <dd>{formatBytes(sample.size_bytes)}</dd>
                <dt>Duration</dt>
                <dd>{formatDuration(sample.duration_seconds)}</dd>
                <dt>Depth</dt>
                <dd>{sample.depth}-bit</dd>
                <dt>Channels</dt>
                <dd>{sample.channels}</dd>
                <dt>Frames</dt>
                <dd>{sample.frames}</dd>
                <dt>Occurrences</dt>
                <dd>{sample.occurrences.length}</dd>
            </dl>
            <h3>Waveform</h3>
            <Waveform sampleHash={sample.hash} peaks={waveform} />
            <h3>Occurrences</h3>
            <table>
                <thead>
                    <tr>
                        <th>Module</th>
                        <th>Tracker</th>
                        <th>Name</th>
                        <th>Rate</th>
                        <th>Volume</th>
                        <th>Panning</th>
                        <th>Loop</th>
                    </tr>
                </thead>
                <tbody>
                    {sample.occurrences.map((occurrence) => (
                        <SampleOccurrenceRow
                            key={`${occurrence.module.hash}-${String(occurrence.properties.occurrence.instrument_index)}-${String(occurrence.properties.occurrence.sample_slot)}`}
                            occurrence={occurrence}
                        />
                    ))}
                </tbody>
            </table>
            <h3>Relations</h3>
            {relations.length === 0 ? (
                <p>No relations found for this sample.</p>
            ) : (
                <table>
                    <thead>
                        <tr>
                            <th>Sample</th>
                            <th>Type</th>
                            <th>Confidence</th>
                            <th>Method</th>
                            <th>Reviewed</th>
                        </tr>
                    </thead>
                    <tbody>
                        {relations.map((relation) => (
                            <SampleRelationRow key={relation.id} relation={relation} subjectHash={sample.hash} />
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
}
