import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SimilarSample } from "../api/samples";
import { classNames } from "../shared/classNames";
import { shortHash } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { RowOpenLink } from "../workspace/RowOpenLink";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { CategoryBadge } from "./CategoryBadge";
import { PlayButton } from "./PlayButton";
import { Thumbnail } from "./Thumbnail";

const DISTANCE_DECIMAL_PLACES = 3;

/** The columns of the neighbors table, as its header and its stacked rows both name them. */
export const SIMILAR_COLUMN_LABELS = {
    sample: "Sample",
    name: "Name",
    category: "Category",
    distance: "Distance",
} as const;

interface SimilarSampleRowProps {
    readonly similar: SimilarSample;
}

/**
 * One spectral neighbor as the detail lists it: its waveform to play it by, or a plain play button
 * while the thumbnail pass has yet to reach it, then its name over its hash, what it is, and how
 * far it sits from the sample in view.
 */
export function SimilarSampleRow({ similar }: SimilarSampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: similar.hash,
    });

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td data-label={SIMILAR_COLUMN_LABELS.sample}>
                {similar.thumbnail === null ? (
                    <PlayButton sampleHash={similar.hash} playbackRateHz={similar.playback_rate_hz}>
                        ▶
                    </PlayButton>
                ) : (
                    <Thumbnail
                        sampleHash={similar.hash}
                        peaks={similar.thumbnail}
                        playbackRateHz={similar.playback_rate_hz}
                    />
                )}
            </td>
            <td className="cell-name" data-label={SIMILAR_COLUMN_LABELS.name}>
                <Link to={href} className="cell-name-stack">
                    <span className="cell-primary">
                        <OptionalLabel value={similar.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
                    </span>
                    <span className="entity-hash mono">{shortHash(similar.hash)}</span>
                </Link>
                <RowOpenLink href={href} label="Open sample" />
            </td>
            <td data-label={SIMILAR_COLUMN_LABELS.category}>
                <CategoryBadge sampleHash={similar.hash} category={similar.category} handLabel={similar.hand_label} />
            </td>
            <td className="mono" data-label={SIMILAR_COLUMN_LABELS.distance}>
                {similar.distance.toFixed(DISTANCE_DECIMAL_PLACES)}
            </td>
        </tr>
    );
}
