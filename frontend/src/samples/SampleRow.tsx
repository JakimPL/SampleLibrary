import type { KeyboardEvent, MouseEvent, ReactElement } from "react";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { SampleSummary } from "../api/samples";
import type { InputMode } from "../layout/layoutMode";
import { classNames } from "../shared/classNames";
import { formatBytes, shortHash } from "../shared/format";
import { useLongPress } from "../shared/gestures/useLongPress";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { RowOpenLink } from "../workspace/RowOpenLink";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { annotationKeyChange } from "./annotationKeys";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { CategoryBadge } from "./CategoryBadge";
import { CategoryCell } from "./CategoryCell";
import { FavoriteToggle } from "./FavoriteToggle";
import { playOnSpace } from "./playKey";
import { RatingStars } from "./RatingStars";
import { RowActionSheet } from "./RowActionSheet";
import type { SampleColumnId } from "./sampleColumns";
import { Thumbnail } from "./Thumbnail";
import { useAnnotationWriter } from "./useAnnotationWriter";
import { samplePreview, useAudioPreview } from "./useAudioPreview";

/** Whether a tap landed on one of the row's own controls, which answer to the tap themselves. */
function isOwnControl(target: EventTarget | null): boolean {
    return target instanceof Element && target.closest("button") !== null;
}

/** Whether the row's click rule took the click as a highlight, which it marks by preventing the click's default. */
function highlightedTheRow(event: MouseEvent<HTMLTableRowElement>): boolean {
    return event.defaultPrevented;
}

interface SampleRowProps {
    readonly sample: SampleSummary;
    /** Whether this row stands for a whole equivalence class, which is how far an edit reaches. */
    readonly groupByEquivalence: boolean;
    /** The columns the listing shows at its width; the name and the waveform are always among them. */
    readonly visibleColumns: ReadonlySet<SampleColumnId>;
    readonly input: InputMode;
}

/**
 * One sample as the listing shows it, and as a person decides about it.
 *
 * The label behind the category, the rating and the favorite mark are all editable here, so working through a
 * library is one pass down the list rather than a detour into each sample in turn. An edit reaches
 * exactly what the row stands for: the whole equivalence class while the listing groups them, and
 * this one sample otherwise. An edit that fails to save says so in the row, the reason in its tooltip.
 * In a narrow listing the category takes the hash's place beneath the name, and under touch the
 * verdict column keeps the heart alone at a finger's size. With the row's link focused, the space
 * bar plays the sample, F flips the favorite mark and a digit rates it, beside the keys every row
 * answers to. A finger's tap on the row takes the sample in hand and plays it in one gesture, its
 * own buttons and chevron keeping their own meaning; a finger held on the row opens a sheet of the
 * same decisions and actions at a tap's size, in place of the modifier clicks and the inline
 * editors a pointer has.
 */
export function SampleRow({ sample, groupByEquivalence, visibleColumns, input }: SampleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick, onKeyDown } = useEntityRowInteractions({
        kind: "sample",
        hash: sample.hash,
    });
    const sent = decisionsOf(sample);
    const annotation = useSampleAnnotation(sample.hash, sent);
    const decisions = annotation ?? { label: null, rating: null, favorite: false };
    const { change, message } = useAnnotationWriter(sample.hash, groupByEquivalence ? "equivalence_class" : "sample");
    const { play } = useAudioPreview();
    const categoryInColumn = visibleColumns.has("category");
    const [actionsOpen, setActionsOpen] = useState(false);
    const longPress = useLongPress(() => {
        setActionsOpen(true);
    }, input === "touch");

    function handleClickCapture(event: MouseEvent<HTMLTableRowElement>): void {
        longPress.onClickCapture(event);
        if (event.defaultPrevented) {
            return;
        }
        onClick(event);
        if (input === "touch" && highlightedTheRow(event) && !isOwnControl(event.target)) {
            play(samplePreview(sample.hash, sample.playback_rate_hz));
        }
    }

    function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
        onKeyDown(event);
        if (event.defaultPrevented || playOnSpace(event, samplePreview(sample.hash, sample.playback_rate_hz), play)) {
            return;
        }
        const keyed = annotationKeyChange(event.key, decisions);
        if (keyed !== null) {
            event.preventDefault();
            change(keyed);
        }
    }

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClickCapture={handleClickCapture}
            onDoubleClick={onDoubleClick}
            onPointerDown={longPress.onPointerDown}
            onPointerMove={longPress.onPointerMove}
            onPointerUp={longPress.onPointerUp}
            onPointerCancel={longPress.onPointerCancel}
        >
            <td>
                <Thumbnail sampleHash={sample.hash} peaks={sample.thumbnail} playbackRateHz={sample.playback_rate_hz} />
                {actionsOpen && (
                    <RowActionSheet
                        sample={sample}
                        decisions={decisions}
                        onChange={change}
                        onClose={() => {
                            setActionsOpen(false);
                        }}
                    />
                )}
            </td>
            <td className="cell-name">
                <Link to={href} className="cell-name-stack" onKeyDown={handleKeyDown}>
                    <span className="cell-primary">
                        <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
                    </span>
                    <span className="entity-hash mono">
                        {categoryInColumn && shortHash(sample.equivalence_class_hash ?? sample.hash)}
                        {sample.equivalence_member_count > 1 && (
                            <span className="badge badge-equivalence">×{sample.equivalence_member_count}</span>
                        )}
                        {!categoryInColumn && (
                            <CategoryBadge
                                sampleHash={sample.hash}
                                category={sample.category}
                                handLabel={sample.hand_label}
                            />
                        )}
                    </span>
                </Link>
                <RowOpenLink href={href} label="Open sample" />
            </td>
            {categoryInColumn && (
                <td className="cell-muted cell-stamp">
                    <CategoryCell
                        sample={sample}
                        label={decisions.label}
                        onCommit={(label) => {
                            change({ label });
                        }}
                        input={input}
                    />
                </td>
            )}
            {visibleColumns.has("verdict") && (
                <td className="cell-verdict">
                    {input === "pointer" && (
                        <RatingStars
                            rating={decisions.rating}
                            onRatingChange={(rating) => {
                                change({ rating });
                            }}
                        />
                    )}
                    <FavoriteToggle
                        favorite={decisions.favorite}
                        onFavoriteChange={(favorite) => {
                            change({ favorite });
                        }}
                    />
                    {message !== null && (
                        <span className="annotation-row-message" role="alert" title={message}>
                            Not saved
                        </span>
                    )}
                </td>
            )}
            {visibleColumns.has("size_bytes") && (
                <td className="cell-muted mono cell-numeric">{formatBytes(sample.size_bytes)}</td>
            )}
            {visibleColumns.has("occurrence_count") && (
                <td className="cell-muted mono cell-numeric">{sample.occurrence_count}</td>
            )}
        </tr>
    );
}
