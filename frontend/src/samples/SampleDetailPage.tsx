import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";

import type { SampleRelation } from "../api/samples";
import { ErrorNotice } from "../shared/ErrorNotice";
import { formatBytes, formatDuration } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL, UNTITLED_MODULE_LABEL } from "../shared/labels";
import { Loading } from "../shared/Loading";
import { OptionalLabel } from "../shared/OptionalLabel";
import { CATEGORY_PLACEHOLDER } from "./category";
import { formatLoop } from "./occurrenceFormat";
import { useSampleDetail } from "./useSampleDetail";
import { Waveform } from "./Waveform";

const CONFIDENCE_DECIMAL_PLACES = 2;

function describeReviewStatus(review: SampleRelation["review"]): string {
    if (!review) {
        return "Unreviewed";
    }

    return review.confirmed ? "Confirmed" : "Rejected";
}

export function SampleDetailPage(): ReactElement {
    const { sampleHash } = useParams<{ sampleHash: string }>();
    const hash = sampleHash ?? "";
    const state = useSampleDetail(hash);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const { sample, relations, waveform } = state.data;
    return (
        <section>
            <h1>
                <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
            </h1>
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
            <h2>Waveform</h2>
            <Waveform sampleHash={sample.hash} peaks={waveform} />
            <h2>Occurrences</h2>
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
                        <tr
                            key={`${occurrence.module.hash}-${String(occurrence.properties.occurrence.instrument_index)}-${String(occurrence.properties.occurrence.sample_slot)}`}
                        >
                            <td>
                                <Link to={`/modules/${occurrence.module.hash}`}>
                                    <OptionalLabel
                                        value={occurrence.module.title}
                                        placeholder={UNTITLED_MODULE_LABEL}
                                    />
                                </Link>{" "}
                                ({occurrence.module.filename})
                            </td>
                            <td>{occurrence.properties.tracker}</td>
                            <td>
                                <OptionalLabel value={occurrence.properties.name} placeholder={UNNAMED_SAMPLE_LABEL} />
                            </td>
                            <td>{occurrence.properties.rate}</td>
                            <td>{occurrence.properties.volume}</td>
                            <td>{occurrence.properties.panning ?? "—"}</td>
                            <td>{formatLoop(occurrence.properties.loop)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <h2>Relations</h2>
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
                        {relations.map((relation) => {
                            const otherHash =
                                relation.subject_hash === hash ? relation.reference_hash : relation.subject_hash;
                            return (
                                <tr key={relation.id}>
                                    <td>
                                        <Link to={`/samples/${otherHash}`}>{otherHash}</Link>
                                    </td>
                                    <td>{relation.relation_type}</td>
                                    <td>{relation.confidence.toFixed(CONFIDENCE_DECIMAL_PLACES)}</td>
                                    <td>{relation.method}</td>
                                    <td>{describeReviewStatus(relation.review)}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}
        </section>
    );
}
