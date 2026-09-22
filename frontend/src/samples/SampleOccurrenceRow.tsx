import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleDetail } from "../api/samples";
import { classNames } from "../shared/classNames";
import { UNNAMED_SAMPLE_LABEL, UNTITLED_MODULE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { RowOpenLink } from "../workspace/RowOpenLink";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { formatLoop } from "./occurrenceFormat";

type SampleOccurrence = SampleDetail["occurrences"][number];

/** The columns of the occurrences table, as its header and its stacked rows both name them. */
export const OCCURRENCE_COLUMN_LABELS = {
    module: "Module",
    tracker: "Tracker",
    name: "Name",
    rate: "Rate",
    volume: "Volume",
    panning: "Panning",
    loop: "Loop",
} as const;

interface SampleOccurrenceRowProps {
    readonly occurrence: SampleOccurrence;
}

export function SampleOccurrenceRow({ occurrence }: SampleOccurrenceRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "module",
        hash: occurrence.module.hash,
    });

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td className="cell-name" data-label={OCCURRENCE_COLUMN_LABELS.module}>
                <Link to={href} className="cell-primary">
                    <OptionalLabel value={occurrence.module.title} placeholder={UNTITLED_MODULE_LABEL} />
                </Link>{" "}
                <span className="cell-muted">({occurrence.module.filename})</span>
                <RowOpenLink href={href} label="Open module" />
            </td>
            <td data-label={OCCURRENCE_COLUMN_LABELS.tracker}>
                <span className={`badge badge-${occurrence.properties.tracker}`}>{occurrence.properties.tracker}</span>
            </td>
            <td className="cell-muted" data-label={OCCURRENCE_COLUMN_LABELS.name}>
                <OptionalLabel value={occurrence.properties.name} placeholder={UNNAMED_SAMPLE_LABEL} />
            </td>
            <td className="mono" data-label={OCCURRENCE_COLUMN_LABELS.rate}>
                {occurrence.properties.rate}
            </td>
            <td className="cell-muted mono" data-label={OCCURRENCE_COLUMN_LABELS.volume}>
                {occurrence.properties.volume}
            </td>
            <td className="cell-muted mono" data-label={OCCURRENCE_COLUMN_LABELS.panning}>
                {occurrence.properties.panning ?? "—"}
            </td>
            <td className="cell-muted" data-label={OCCURRENCE_COLUMN_LABELS.loop}>
                {formatLoop(occurrence.properties.loop)}
            </td>
        </tr>
    );
}
