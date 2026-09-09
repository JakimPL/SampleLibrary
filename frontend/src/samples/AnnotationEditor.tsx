import { type ReactElement, useState } from "react";

import type { SampleDetail } from "../api/samples";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { FavoriteToggle } from "./FavoriteToggle";
import { LabelField } from "./LabelField";
import { RatingStars } from "./RatingStars";
import { useAnnotationWriter } from "./useAnnotationWriter";

const SMALLEST_GROUP = 1;

interface AnnotationEditorProps {
    readonly sample: SampleDetail;
}

/**
 * Where a person says what a sample is and what they make of it.
 *
 * Every decision writes as it is made -- a star and the favorite mark on the click, the wording on
 * Enter or on leaving the field -- which is the same gesture the samples listing answers to, so one
 * habit works wherever a sample is met.
 *
 * Every write sends all three decisions together, so what the sample carries afterwards is exactly
 * what is on screen. Where the sample has near-duplicates the same state reaches all of them by
 * default, which is how the listing already groups them; each one is recorded on its own, so the
 * group boundary moving later leaves every decision standing.
 */
export function AnnotationEditor({ sample }: AnnotationEditorProps): ReactElement {
    const current = useSampleAnnotation(sample.hash, decisionsOf(sample));
    const [reachesGroup, setReachesGroup] = useState(sample.equivalence_member_count > SMALLEST_GROUP);
    const { write, isSaving, message } = useAnnotationWriter(
        sample.hash,
        reachesGroup ? "equivalence_class" : "sample",
    );

    const label = current?.label ?? null;
    const rating = current?.rating ?? null;
    const favorite = current?.favorite ?? false;

    return (
        <div className="annotation-editor">
            <div className="annotation-editor-row">
                <LabelField
                    key={label ?? ""}
                    label={label}
                    isSaving={isSaving}
                    onCommit={(next) => {
                        write({ label: next, rating, favorite });
                    }}
                    onLeave={() => undefined}
                    takesFocus={false}
                />
                <button
                    type="button"
                    disabled={isSaving || label === null}
                    onClick={() => {
                        write({ label: null, rating, favorite });
                    }}
                >
                    Clear
                </button>
            </div>
            <div className="annotation-editor-row">
                <RatingStars
                    rating={rating}
                    isSaving={isSaving}
                    onRatingChange={(next) => {
                        write({ label, rating: next, favorite });
                    }}
                />
                <FavoriteToggle
                    favorite={favorite}
                    isSaving={isSaving}
                    onFavoriteChange={(next) => {
                        write({ label, rating, favorite: next });
                    }}
                />
                {sample.equivalence_member_count > SMALLEST_GROUP && (
                    <label className="annotation-editor-scope">
                        <input
                            type="checkbox"
                            checked={reachesGroup}
                            onChange={(event) => {
                                setReachesGroup(event.target.checked);
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
