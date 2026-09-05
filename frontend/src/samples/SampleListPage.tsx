import type { ReactElement } from "react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorNotice } from "../shared/ErrorNotice";
import { formatBytes } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { Loading } from "../shared/Loading";
import { OptionalLabel } from "../shared/OptionalLabel";
import { CATEGORY_PLACEHOLDER } from "./category";
import { useSampleList } from "./useSampleList";

const PAGE_SIZE = 50;

export function SampleListPage(): ReactElement {
    const [offset, setOffset] = useState(0);
    const state = useSampleList({ limit: PAGE_SIZE, offset });

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const { items, total } = state.data;
    return (
        <section>
            <h1>Samples</h1>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Category</th>
                        <th>Size</th>
                        <th>Occurrences</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((sample) => (
                        <tr key={sample.hash}>
                            <td>
                                <Link to={`/samples/${sample.hash}`}>
                                    <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
                                </Link>
                            </td>
                            <td>{CATEGORY_PLACEHOLDER}</td>
                            <td>{formatBytes(sample.size_bytes)}</td>
                            <td>{sample.occurrence_count}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <nav aria-label="pagination">
                <button
                    type="button"
                    disabled={offset === 0}
                    onClick={() => {
                        setOffset(Math.max(0, offset - PAGE_SIZE));
                    }}
                >
                    Previous
                </button>
                <span>
                    {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
                </span>
                <button
                    type="button"
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => {
                        setOffset(offset + PAGE_SIZE);
                    }}
                >
                    Next
                </button>
            </nav>
        </section>
    );
}
