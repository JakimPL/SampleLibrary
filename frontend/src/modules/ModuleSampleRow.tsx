import type { MouseEvent, ReactElement } from "react";
import { Link } from "react-router-dom";

import type { ModuleDetail } from "../api/modules";
import { useLayoutMode } from "../layout/useLayoutMode";
import { formatLoop } from "../samples/occurrenceFormat";
import { Thumbnail } from "../samples/Thumbnail";
import { samplePreview, useAudioPreview } from "../samples/useAudioPreview";
import { classNames } from "../shared/classNames";
import { formatBytes } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { RowOpenLink } from "../workspace/RowOpenLink";
import { tapPlays } from "../workspace/rowTap";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";

type ModuleOccurrence = ModuleDetail["occurrences"][number];

/** The columns of a module's samples table, as its header and its stacked rows both name them. */
export const MODULE_SAMPLE_COLUMN_LABELS = {
    waveform: "Waveform",
    name: "Name",
    instrument: "Instrument",
    slot: "Slot",
    rate: "Rate",
    volume: "Volume",
    panning: "Panning",
    loop: "Loop",
    size: "Size",
    depth: "Depth",
} as const;

interface ModuleSampleRowProps {
    readonly occurrence: ModuleOccurrence;
}

/**
 * One sample of a module as its detail lists it: its waveform to play it by at the rate the slot
 * sets, its name, and what the slot says of it. A finger's tap on the row takes the sample in hand
 * and plays it at that rate; a double-click opens it.
 */
export function ModuleSampleRow({ occurrence }: ModuleSampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: occurrence.sample.hash,
    });
    const { input } = useLayoutMode();
    const { play } = useAudioPreview();

    function handleClickCapture(event: MouseEvent<HTMLTableRowElement>): void {
        onClick(event);
        if (tapPlays(input, event)) {
            play(samplePreview(occurrence.sample.hash, occurrence.properties.rate));
        }
    }

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClickCapture={handleClickCapture}
            onDoubleClick={onDoubleClick}
        >
            <td data-label={MODULE_SAMPLE_COLUMN_LABELS.waveform}>
                <Thumbnail
                    sampleHash={occurrence.sample.hash}
                    peaks={occurrence.sample.thumbnail}
                    playbackRateHz={occurrence.properties.rate}
                />
            </td>
            <td className="cell-name" data-label={MODULE_SAMPLE_COLUMN_LABELS.name}>
                <Link to={href} className="cell-primary">
                    <OptionalLabel value={occurrence.properties.name} placeholder={UNNAMED_SAMPLE_LABEL} />
                </Link>
                <RowOpenLink href={href} label="Open sample" />
            </td>
            <td className="cell-muted mono" data-label={MODULE_SAMPLE_COLUMN_LABELS.instrument}>
                {occurrence.properties.occurrence.instrument_index}
            </td>
            <td className="cell-muted mono" data-label={MODULE_SAMPLE_COLUMN_LABELS.slot}>
                {occurrence.properties.occurrence.sample_slot}
            </td>
            <td className="mono" data-label={MODULE_SAMPLE_COLUMN_LABELS.rate}>
                {occurrence.properties.rate}
            </td>
            <td className="cell-muted mono" data-label={MODULE_SAMPLE_COLUMN_LABELS.volume}>
                {occurrence.properties.volume}
            </td>
            <td className="cell-muted mono" data-label={MODULE_SAMPLE_COLUMN_LABELS.panning}>
                {occurrence.properties.panning ?? "—"}
            </td>
            <td className="cell-muted" data-label={MODULE_SAMPLE_COLUMN_LABELS.loop}>
                {formatLoop(occurrence.properties.loop)}
            </td>
            <td className="cell-muted mono" data-label={MODULE_SAMPLE_COLUMN_LABELS.size}>
                {formatBytes(occurrence.sample.size_bytes)}
            </td>
            <td className="cell-muted mono" data-label={MODULE_SAMPLE_COLUMN_LABELS.depth}>
                {occurrence.sample.depth}-bit
            </td>
        </tr>
    );
}
