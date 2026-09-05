import type { ReactElement } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorNotice } from "../shared/ErrorNotice";
import { Loading } from "../shared/Loading";
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
            <h1>{module.title}</h1>
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
            </dl>
            <h2>Samples</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Instrument</th>
                        <th>Slot</th>
                        <th>Rate</th>
                    </tr>
                </thead>
                <tbody>
                    {module.occurrences.map((occurrence) => (
                        <tr
                            key={`${String(occurrence.occurrence.instrument_index)}-${String(occurrence.occurrence.sample_slot)}`}
                        >
                            <td>
                                <Link to={`/samples/${occurrence.sample_hash}`}>{occurrence.name}</Link>
                            </td>
                            <td>{occurrence.occurrence.instrument_index}</td>
                            <td>{occurrence.occurrence.sample_slot}</td>
                            <td>{occurrence.rate}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </section>
    );
}
