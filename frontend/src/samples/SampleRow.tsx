import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleSummary } from "../api/samples";
import { classNames } from "../shared/classNames";
import { formatBytes, shortHash } from "../shared/format";
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
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Thumbnail sampleHash={sample.hash} peaks={sample.thumbnail} />
            </td>
            <td className="cell-name">
                <Link to={href} className="cell-name-stack">
                    <span className="cell-primary">
                        <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
                    </span>
                    <span className="entity-hash mono">
                        {shortHash(sample.equivalence_class_hash ?? sample.hash)}
                        {sample.equivalence_member_count > 1 && (
                            <span className="badge badge-equivalence">×{sample.equivalence_member_count}</span>
                        )}
                    </span>
                </Link>
            </td>
            <td className="cell-muted">{CATEGORY_PLACEHOLDER}</td>
            <td className="cell-muted mono">{formatBytes(sample.size_bytes)}</td>
            <td className="cell-muted mono">{sample.occurrence_count}</td>
        </tr>
    );
}
