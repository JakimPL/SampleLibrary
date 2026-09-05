import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorNotice } from "../shared/ErrorNotice";
import { Loading } from "../shared/Loading";
import { useSampleDetail } from "./useSampleDetail";

const CONFIDENCE_DECIMAL_PLACES = 2;

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

    const { sample, relations } = state.data;
    return (
        <section>
            <h1>Sample {sample.hash}</h1>
            <dl>
                <dt>Depth</dt>
                <dd>{sample.depth}-bit</dd>
                <dt>Channels</dt>
                <dd>{sample.channels}</dd>
                <dt>Frames</dt>
                <dd>{sample.frames}</dd>
            </dl>
            <h2>Occurrences</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Module</th>
                        <th>Instrument</th>
                        <th>Slot</th>
                    </tr>
                </thead>
                <tbody>
                    {sample.occurrences.map((occurrence) => (
                        <tr
                            key={`${occurrence.occurrence.module_hash}-${String(occurrence.occurrence.instrument_index)}-${String(occurrence.occurrence.sample_slot)}`}
                        >
                            <td>{occurrence.name}</td>
                            <td>
                                <Link to={`/modules/${occurrence.occurrence.module_hash}`}>
                                    {occurrence.occurrence.module_hash}
                                </Link>
                            </td>
                            <td>{occurrence.occurrence.instrument_index}</td>
                            <td>{occurrence.occurrence.sample_slot}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <h2>Relations</h2>
            <table>
                <thead>
                    <tr>
                        <th>Sample</th>
                        <th>Type</th>
                        <th>Confidence</th>
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
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </section>
    );
}
