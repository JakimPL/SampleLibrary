import type { ReactElement } from "react";

import type { SampleSummary } from "../api/samples";
import { SampleRow } from "./SampleRow";

interface SamplesTableProps {
    readonly samples: readonly SampleSummary[];
    readonly total: number;
    readonly offset: number;
    readonly limit: number;
    readonly onOffsetChange: (offset: number) => void;
}

export function SamplesTable({ samples, total, offset, limit, onOffsetChange }: SamplesTableProps): ReactElement {
    return (
        <>
            <table>
                <thead>
                    <tr>
                        <th>Waveform</th>
                        <th>Name</th>
                        <th>Category</th>
                        <th>Size</th>
                        <th>Occurrences</th>
                    </tr>
                </thead>
                <tbody>
                    {samples.map((sample) => (
                        <SampleRow key={sample.hash} sample={sample} />
                    ))}
                </tbody>
            </table>
            <nav aria-label="pagination">
                <button
                    type="button"
                    disabled={offset === 0}
                    onClick={() => {
                        onOffsetChange(Math.max(0, offset - limit));
                    }}
                >
                    Previous
                </button>
                <span>
                    {offset + 1}–{Math.min(offset + limit, total)} of {total}
                </span>
                <button
                    type="button"
                    disabled={offset + limit >= total}
                    onClick={() => {
                        onOffsetChange(offset + limit);
                    }}
                >
                    Next
                </button>
            </nav>
        </>
    );
}
