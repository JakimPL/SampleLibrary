import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleDetail } from "../api/samples";
import { classNames } from "../shared/classNames";
import { UNNAMED_SAMPLE_LABEL, UNTITLED_MODULE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { formatLoop } from "./occurrenceFormat";

type SampleOccurrence = SampleDetail["occurrences"][number];

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
            onClick={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Link to={href}>
                    <OptionalLabel value={occurrence.module.title} placeholder={UNTITLED_MODULE_LABEL} />
                </Link>{" "}
                ({occurrence.module.filename})
            </td>
            <td>{occurrence.properties.tracker}</td>
            <td>
                <OptionalLabel value={occurrence.properties.name} placeholder={UNNAMED_SAMPLE_LABEL} />
            </td>
            <td>{occurrence.properties.rate}</td>
            <td>{occurrence.properties.volume}</td>
            <td>{occurrence.properties.panning ?? "—"}</td>
            <td>{formatLoop(occurrence.properties.loop)}</td>
        </tr>
    );
}
