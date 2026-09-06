import type { ReactElement } from "react";

import type { SampleDetail, SampleRelation, SimilarSample } from "../api/samples";
import { formatBytes, formatDuration } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { SpectralDistanceReadout } from "../workspace/panels/SpectralDistanceReadout";
import { CATEGORY_PLACEHOLDER } from "./category";
import { SampleOccurrenceRow } from "./SampleOccurrenceRow";
import { SampleRelationRow } from "./SampleRelationRow";
import { SimilarSampleRow } from "./SimilarSampleRow";

interface SampleDetailViewProps {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
    readonly similar: readonly SimilarSample[];
}

export function SampleDetailView({ sample, relations, similar }: SampleDetailViewProps): ReactElement {
    return (
        <section className="detail-scroll">
            <h2>
                <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
            </h2>
            <p className="hash mono cell-muted">{sample.hash}</p>
            <SpectralDistanceReadout />
            <dl className="kv">
                <dt>Category</dt>
                <dd>{CATEGORY_PLACEHOLDER}</dd>
                <dt>Size</dt>
                <dd className="mono">{formatBytes(sample.size_bytes)}</dd>
                <dt>Duration</dt>
                <dd className="mono">{formatDuration(sample.duration_seconds)}</dd>
                <dt>Depth</dt>
                <dd className="mono">{sample.depth}-bit</dd>
                <dt>Channels</dt>
                <dd className="mono">{sample.channels}</dd>
                <dt>Frames</dt>
                <dd className="mono">{sample.frames}</dd>
                <dt>Occurrences</dt>
                <dd className="mono">{sample.occurrences.length}</dd>
            </dl>
            <div className="detail-section">
                <h3>Occurrences</h3>
                <table className="mini">
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
            </div>
            <div className="detail-section">
                <h3>Relations</h3>
                {relations.length === 0 ? (
                    <p className="placeholder-box">No relations found for this sample.</p>
                ) : (
                    <table className="mini">
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
            </div>
            <div className="detail-section">
                <h3>Similar Samples</h3>
                {similar.length === 0 ? (
                    <p className="placeholder-box">
                        No spectral neighbors yet — run the embedding pipeline to populate this.
                    </p>
                ) : (
                    <table className="mini">
                        <thead>
                            <tr>
                                <th>Play</th>
                                <th>Sample</th>
                                <th>Distance</th>
                            </tr>
                        </thead>
                        <tbody>
                            {similar.map((neighbor) => (
                                <SimilarSampleRow key={neighbor.hash} similar={neighbor} />
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
            <div className="detail-section">
                <h3>Frequently Co-occurs With</h3>
                <p className="placeholder-box">Awaits a co-occurrence analysis across the catalog.</p>
            </div>
        </section>
    );
}
