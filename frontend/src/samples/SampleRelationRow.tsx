import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleRelation } from "../api/samples";
import { classNames } from "../shared/classNames";
import { RowOpenLink } from "../workspace/RowOpenLink";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";

const CONFIDENCE_DECIMAL_PLACES = 2;

/** The columns of the relations table, as its header and its stacked rows both name them. */
export const RELATION_COLUMN_LABELS = {
    sample: "Sample",
    type: "Type",
    confidence: "Confidence",
    method: "Method",
    reviewed: "Reviewed",
} as const;

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
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td className="cell-name" data-label={RELATION_COLUMN_LABELS.sample}>
                <Link to={href} className="cell-primary mono">
                    {otherHash}
                </Link>
                <RowOpenLink href={href} label="Open sample" />
            </td>
            <td data-label={RELATION_COLUMN_LABELS.type}>
                <span className={`badge badge-${relation.relation_type}`}>{relation.relation_type}</span>
            </td>
            <td className="mono" data-label={RELATION_COLUMN_LABELS.confidence}>
                {relation.confidence.toFixed(CONFIDENCE_DECIMAL_PLACES)}
            </td>
            <td className="cell-muted" data-label={RELATION_COLUMN_LABELS.method}>
                {relation.method}
            </td>
            <td className="cell-muted" data-label={RELATION_COLUMN_LABELS.reviewed}>
                {describeReviewStatus(relation.review)}
            </td>
        </tr>
    );
}
