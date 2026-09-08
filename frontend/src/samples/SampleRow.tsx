import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleSummary } from "../api/samples";
import { classNames } from "../shared/classNames";
import { formatBytes, shortHash } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { CategoryBadge } from "./CategoryBadge";
import { REFERENCE_NOTE } from "./nominalRate";
import { ratingGlyphs } from "./rating";
import { Thumbnail } from "./Thumbnail";
import type { PreviewPitch } from "./useAudioPreview";

/** The pitch a listing row previews at: the rate this sample is mostly declared at, sounded at
 * the note the library mostly plays it at. */
function previewPitchFor(sample: SampleSummary): PreviewPitch | null {
    return sample.dominant_rate_hz === null
        ? null
        : { rateHz: sample.dominant_rate_hz, soundedNote: sample.dominant_note ?? REFERENCE_NOTE };
}

/** What a rating reads as to a screen reader, where the stars alone would say nothing. */
function ratingLabel(rating: number | null): string {
    return rating === null ? "Unrated" : `Rated ${String(rating)}`;
}

interface SampleRowProps {
    readonly sample: SampleSummary;
}

export function SampleRow({ sample }: SampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: sample.hash,
    });
    const annotation = useSampleAnnotation(sample.hash, decisionsOf(sample));

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Thumbnail sampleHash={sample.hash} peaks={sample.thumbnail} pitch={previewPitchFor(sample)} />
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
            <td className="cell-muted">
                <CategoryBadge sampleHash={sample.hash} category={sample.category} handLabel={sample.hand_label} />
            </td>
            <td className="cell-muted cell-verdict">
                {annotation?.favorite === true && (
                    <span className="favorite-mark" title="Favorite" aria-label="Favorite">
                        ♥
                    </span>
                )}
                <span className="rating-mark" aria-label={ratingLabel(annotation?.rating ?? null)}>
                    {ratingGlyphs(annotation?.rating ?? null)}
                </span>
            </td>
            <td className="cell-muted mono">{formatBytes(sample.size_bytes)}</td>
            <td className="cell-muted mono">{sample.occurrence_count}</td>
        </tr>
    );
}
