import type { ReactElement } from "react";

import type { AnnotationScope } from "../api/curation";
import type { SampleDetail } from "../api/samples";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { FavoriteToggle } from "./FavoriteToggle";
import { LabelField } from "./LabelField";
import { RatingStars } from "./RatingStars";
import { useAnnotationWriter } from "./useAnnotationWriter";

const SMALLEST_GROUP = 1;

interface AnnotationEditorProps {
    readonly sample: SampleDetail;
    /** How far a decision made here reaches, which the near-duplicates checkbox sets for every gesture on the sample. */
    readonly scope: AnnotationScope;
    readonly onScopeChange: (scope: AnnotationScope) => void;
}

/** How far a decision about this sample reaches by default: its whole group of near-duplicates, where it has one. */
export function defaultScopeFor(sample: SampleDetail): AnnotationScope {
    return sample.equivalence_member_count > SMALLEST_GROUP ? "equivalence_class" : "sample";
}

/**
 * Where a person says what a sample is and what they make of it.
 *
 * Every decision writes as it is made -- a star and the favorite mark on the click, the wording on
 * Enter or on leaving the field -- which is the same gesture the samples listing answers to, so one
 * habit works wherever a sample is met. Each gesture changes the one decision it is about and keeps
 * the others. Where the sample has near-duplicates a decision reaches all of them by default, which
 * is how the listing already groups them; each one is recorded on its own, so the group boundary
 * moving later leaves every decision standing.
 */
export function AnnotationEditor({ sample, scope, onScopeChange }: AnnotationEditorProps): ReactElement {
    const current = useSampleAnnotation(sample.hash, decisionsOf(sample));
    const { change, message } = useAnnotationWriter(sample.hash, scope);

    const label = current?.label ?? null;
    const rating = current?.rating ?? null;
    const favorite = current?.favorite ?? false;

    return (
        <div className="annotation-editor">
            <div className="annotation-editor-row">
                <LabelField
                    key={label ?? ""}
                    label={label}
                    onCommit={(next) => {
                        change({ label: next });
                    }}
                    onLeave={() => undefined}
                    takesFocus={false}
                />
                <button
                    type="button"
                    disabled={label === null}
                    onClick={() => {
                        change({ label: null });
                    }}
                >
                    Clear
                </button>
            </div>
            <div className="annotation-editor-row">
                <RatingStars
                    rating={rating}
                    onRatingChange={(next) => {
                        change({ rating: next });
                    }}
                />
                <FavoriteToggle
                    favorite={favorite}
                    onFavoriteChange={(next) => {
                        change({ favorite: next });
                    }}
                />
                {sample.equivalence_member_count > SMALLEST_GROUP && (
                    <label className="annotation-editor-scope">
                        <input
                            type="checkbox"
                            checked={scope === "equivalence_class"}
                            onChange={(event) => {
                                onScopeChange(event.target.checked ? "equivalence_class" : "sample");
                            }}
                        />
                        Apply to all {sample.equivalence_member_count} near-duplicates
                    </label>
                )}
            </div>
            {message !== null && <p className="annotation-editor-message">{message}</p>}
        </div>
    );
}
