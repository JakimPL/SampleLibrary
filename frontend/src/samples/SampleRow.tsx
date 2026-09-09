import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { SampleSummary } from "../api/samples";
import { classNames } from "../shared/classNames";
import { formatBytes, shortHash } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { CategoryCell } from "./CategoryCell";
import { FavoriteToggle } from "./FavoriteToggle";
import { RatingStars } from "./RatingStars";
import { Thumbnail } from "./Thumbnail";
import { useAnnotationWriter } from "./useAnnotationWriter";

interface SampleRowProps {
    readonly sample: SampleSummary;
    /** Whether this row stands for a whole equivalence class, which is how far an edit reaches. */
    readonly groupByEquivalence: boolean;
}

/**
 * One sample as the listing shows it, and as a person decides about it.
 *
 * The category, the rating and the favorite mark are all editable here, so working through a
 * library is one pass down the list rather than a detour into each sample in turn. An edit reaches
 * exactly what the row stands for: the whole equivalence class while the listing groups them, and
 * this one sample otherwise.
 */
export function SampleRow({ sample, groupByEquivalence }: SampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: sample.hash,
    });
    const sent = decisionsOf(sample);
    const annotation = useSampleAnnotation(sample.hash, sent);
    const decisions = annotation ?? { label: null, rating: null, favorite: false };
    const { write, isSaving } = useAnnotationWriter(sample.hash, groupByEquivalence ? "equivalence_class" : "sample");

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Thumbnail sampleHash={sample.hash} peaks={sample.thumbnail} playbackRateHz={sample.playback_rate_hz} />
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
                <CategoryCell sample={sample} decisions={decisions} isSaving={isSaving} onCommit={write} />
            </td>
            <td className="cell-verdict">
                <RatingStars
                    rating={decisions.rating}
                    isSaving={isSaving}
                    onRatingChange={(rating) => {
                        write({ ...decisions, rating });
                    }}
                />
                <FavoriteToggle
                    favorite={decisions.favorite}
                    isSaving={isSaving}
                    onFavoriteChange={(favorite) => {
                        write({ ...decisions, favorite });
                    }}
                />
            </td>
            <td className="cell-muted mono">{formatBytes(sample.size_bytes)}</td>
            <td className="cell-muted mono">{sample.occurrence_count}</td>
        </tr>
    );
}
