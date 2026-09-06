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
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Thumbnail sampleHash={occurrence.sample.hash} peaks={occurrence.sample.thumbnail} />
            </td>
            <td className="cell-name">
                <Link to={href} className="cell-primary">
                    <OptionalLabel value={occurrence.properties.name} placeholder={UNNAMED_SAMPLE_LABEL} />
                </Link>
            </td>
            <td className="cell-muted mono">{occurrence.properties.occurrence.instrument_index}</td>
            <td className="cell-muted mono">{occurrence.properties.occurrence.sample_slot}</td>
            <td className="mono">{occurrence.properties.rate}</td>
            <td className="cell-muted mono">{occurrence.properties.volume}</td>
            <td className="cell-muted mono">{occurrence.properties.panning ?? "—"}</td>
            <td className="cell-muted">{formatLoop(occurrence.properties.loop)}</td>
            <td className="cell-muted mono">{formatBytes(occurrence.sample.size_bytes)}</td>
            <td className="cell-muted mono">{occurrence.sample.depth}-bit</td>
        </tr>
    );
}
