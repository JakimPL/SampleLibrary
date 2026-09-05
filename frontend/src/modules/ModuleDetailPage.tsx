import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";

import { formatLoop } from "../samples/occurrenceFormat";
import { Thumbnail } from "../samples/Thumbnail";
import { ErrorNotice } from "../shared/ErrorNotice";
import { formatBytes } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL, UNTITLED_MODULE_LABEL } from "../shared/labels";
import { Loading } from "../shared/Loading";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useModule } from "./useModule";

export function ModuleDetailPage(): ReactElement {
    const { moduleHash } = useParams<{ moduleHash: string }>();
    const state = useModule(moduleHash ?? "");

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const module = state.data;
    return (
        <section>
            <h1>
                <OptionalLabel value={module.title} placeholder={UNTITLED_MODULE_LABEL} />
            </h1>
            <dl>
                <dt>Filename</dt>
                <dd>{module.filename}</dd>
                <dt>Tracker</dt>
                <dd>{module.tracker}</dd>
                <dt>Channels</dt>
                <dd>{module.channel_count}</dd>
                <dt>Patterns</dt>
                <dd>{module.pattern_count}</dd>
                <dt>Instruments</dt>
                <dd>{module.instrument_count}</dd>
                <dt>Samples</dt>
                <dd>{module.sample_count}</dd>
                <dt>File Size</dt>
                <dd>{formatBytes(module.file_size)}</dd>
                <dt>Ingested At</dt>
                <dd>{new Date(module.ingested_at).toLocaleString()}</dd>
            </dl>
            <h2>Samples</h2>
            <table>
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
                        <tr
                            key={`${String(occurrence.properties.occurrence.instrument_index)}-${String(occurrence.properties.occurrence.sample_slot)}`}
                        >
                            <td>
                                <Thumbnail sampleHash={occurrence.sample.hash} peaks={occurrence.sample.thumbnail} />
                            </td>
                            <td>
                                <Link to={`/samples/${occurrence.sample.hash}`}>
                                    <OptionalLabel
                                        value={occurrence.properties.name}
                                        placeholder={UNNAMED_SAMPLE_LABEL}
                                    />
                                </Link>
                            </td>
                            <td>{occurrence.properties.occurrence.instrument_index}</td>
                            <td>{occurrence.properties.occurrence.sample_slot}</td>
                            <td>{occurrence.properties.rate}</td>
                            <td>{occurrence.properties.volume}</td>
                            <td>{occurrence.properties.panning ?? "—"}</td>
                            <td>{formatLoop(occurrence.properties.loop)}</td>
                            <td>{formatBytes(occurrence.sample.size_bytes)}</td>
                            <td>{occurrence.sample.depth}-bit</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </section>
    );
}
