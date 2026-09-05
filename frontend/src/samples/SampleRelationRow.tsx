import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleRelation } from "../api/samples";
import { classNames } from "../shared/classNames";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";

const CONFIDENCE_DECIMAL_PLACES = 2;

function describeReviewStatus(review: SampleRelation["review"]): string {
    if (!review) {
        return "Unreviewed";
    }

    return review.confirmed ? "Confirmed" : "Rejected";
}

interface SampleRelationRowProps {
    readonly relation: SampleRelation;
    readonly subjectHash: string;
}

export function SampleRelationRow({ relation, subjectHash }: SampleRelationRowProps): ReactElement {
    const otherHash = relation.subject_hash === subjectHash ? relation.reference_hash : relation.subject_hash;
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: otherHash,
    });

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClick={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Link to={href}>{otherHash}</Link>
            </td>
            <td>{relation.relation_type}</td>
            <td>{relation.confidence.toFixed(CONFIDENCE_DECIMAL_PLACES)}</td>
            <td>{relation.method}</td>
            <td>{describeReviewStatus(relation.review)}</td>
        </tr>
    );
}
