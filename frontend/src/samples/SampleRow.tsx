import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleSummary } from "../api/samples";
import { classNames } from "../shared/classNames";
import { formatBytes } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { CATEGORY_PLACEHOLDER } from "./category";
import { Thumbnail } from "./Thumbnail";

interface SampleRowProps {
    readonly sample: SampleSummary;
}

export function SampleRow({ sample }: SampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: sample.hash,
    });

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClick={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Thumbnail sampleHash={sample.hash} peaks={sample.thumbnail} />
            </td>
            <td>
                <Link to={href}>
                    <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
                </Link>
            </td>
            <td>{CATEGORY_PLACEHOLDER}</td>
            <td>{formatBytes(sample.size_bytes)}</td>
            <td>{sample.occurrence_count}</td>
        </tr>
    );
}
