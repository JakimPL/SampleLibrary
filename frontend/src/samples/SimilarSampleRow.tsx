import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SimilarSample } from "../api/samples";
import { classNames } from "../shared/classNames";
import { shortHash } from "../shared/format";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";

const DISTANCE_DECIMAL_PLACES = 3;

interface SimilarSampleRowProps {
    readonly similar: SimilarSample;
}

export function SimilarSampleRow({ similar }: SimilarSampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: similar.hash,
    });

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClick={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td className="cell-name">
                <Link to={href} className="cell-primary mono">
                    {shortHash(similar.hash)}
                </Link>
            </td>
            <td className="mono">{similar.distance.toFixed(DISTANCE_DECIMAL_PLACES)}</td>
        </tr>
    );
}
