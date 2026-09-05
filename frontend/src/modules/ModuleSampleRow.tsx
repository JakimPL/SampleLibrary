import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { ModuleDetail } from "../api/modules";
import { formatLoop } from "../samples/occurrenceFormat";
import { Thumbnail } from "../samples/Thumbnail";
import { classNames } from "../shared/classNames";
import { formatBytes } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";

type ModuleOccurrence = ModuleDetail["occurrences"][number];

interface ModuleSampleRowProps {
    readonly occurrence: ModuleOccurrence;
}

export function ModuleSampleRow({ occurrence }: ModuleSampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: occurrence.sample.hash,
    });

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClick={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Thumbnail sampleHash={occurrence.sample.hash} peaks={occurrence.sample.thumbnail} />
            </td>
            <td>
                <Link to={href}>
                    <OptionalLabel value={occurrence.properties.name} placeholder={UNNAMED_SAMPLE_LABEL} />
                </Link>
            </td>
            <td>{occurrence.properties.occurrence.instrument_index}</td>
            <td>{occurrence.properties.occurrence.sample_slot}</td>
            <td>{occurrence.properties.rate}</td>
            <td>{occurrence.properties.volume}</td>
            <td>{occurrence.properties.panning ?? "—"}</td>
            <td>{formatLoop(occurrence.properties.loop)}</td>
            <td>{formatBytes(occurrence.sample.size_bytes)}</td>
            <td>{occurrence.sample.depth}-bit</td>
        </tr>
    );
}
