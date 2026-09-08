import { type ReactElement, useCallback, useState } from "react";

import {
    type AnnotationDecisions,
    type AnnotationWritten,
    getLabelVocabulary,
    setSampleAnnotation,
} from "../api/curation";
import type { SampleDetail } from "../api/samples";
import { describeError } from "../shared/fetchState";
import { invalidateRequest } from "../shared/requestCache";
import { useFetch } from "../shared/useFetch";
import { decisionsOf, useAnnotationStore, useSampleAnnotation } from "./annotationStore";
import { FavoriteToggle } from "./FavoriteToggle";
import { RatingStars } from "./RatingStars";
import { sampleDetailCacheKey } from "./useSampleDetail";
import { sampleHoverCacheKey } from "./useSampleHoverPreview";

const VOCABULARY_CACHE_KEY = "label-vocabulary";
const VOCABULARY_LIST_ID = "sample-label-vocabulary";
const SMALLEST_GROUP = 1;

interface AnnotationEditorProps {
    readonly sample: SampleDetail;
}

function forgetCachedSamples(sampleHashes: readonly string[]): void {
    for (const sampleHash of sampleHashes) {
        invalidateRequest(sampleDetailCacheKey(sampleHash));
        invalidateRequest(sampleHoverCacheKey(sampleHash));
    }
}

/**
 * Where a person says what a sample is and what they make of it.
 *
 * The wording is free text, and the list of what has already been used is offered back rather than
 * enforced, so one vocabulary settles by habit instead of by a schema nobody has designed yet. The
 * rating and the favorite mark write as soon as they are clicked, the label on an explicit save,
 * which is the difference between choosing from a scale and finishing a thought.
 *
 * Every write sends all three decisions together, so what the sample carries afterwards is exactly
 * what is on screen. Where the sample has near-duplicates the same state reaches all of them by
 * default, which is how the listing already groups them; each one is recorded on its own, so the
 * group boundary moving later leaves every decision standing.
 */
export function AnnotationEditor({ sample }: AnnotationEditorProps): ReactElement {
    const current = useSampleAnnotation(sample.hash, decisionsOf(sample));
    const applyAnnotation = useAnnotationStore((state) => state.applyAnnotation);
    const vocabulary = useFetch(getLabelVocabulary, [], VOCABULARY_CACHE_KEY);
    const [text, setText] = useState(current?.label ?? "");
    const [reachesGroup, setReachesGroup] = useState(sample.equivalence_member_count > SMALLEST_GROUP);
    const [isSaving, setIsSaving] = useState(false);
    const [message, setMessage] = useState<string | null>(null);

    const run = useCallback(
        (operation: Promise<AnnotationWritten>): void => {
            setIsSaving(true);
            setMessage(null);
            operation
                .then((written) => {
                    applyAnnotation(written.sample_hashes, written.annotation);
                    forgetCachedSamples(written.sample_hashes);
                    invalidateRequest(VOCABULARY_CACHE_KEY);
                })
                .catch((error: unknown) => {
                    setMessage(describeError(error));
                })
                .finally(() => {
                    setIsSaving(false);
                });
        },
        [applyAnnotation],
    );

    const scope = reachesGroup ? "equivalence_class" : "sample";
    const label = current?.label ?? null;
    const rating = current?.rating ?? null;
    const favorite = current?.favorite ?? false;
    const trimmed = text.trim();

    const write = (decisions: AnnotationDecisions): void => {
        run(setSampleAnnotation(sample.hash, decisions, scope));
    };

    return (
        <div className="annotation-editor">
            <div className="annotation-editor-row">
                <input
                    className="annotation-editor-input"
                    type="text"
                    list={VOCABULARY_LIST_ID}
                    placeholder="What is this sample?"
                    value={text}
                    aria-label="Hand label"
                    onChange={(event) => {
                        setText(event.target.value);
                    }}
                />
                <datalist id={VOCABULARY_LIST_ID}>
                    {vocabulary.status === "success" &&
                        vocabulary.data.map((known) => <option key={known} value={known} />)}
                </datalist>
                <button
                    type="button"
                    disabled={isSaving || trimmed === ""}
                    onClick={() => {
                        write({ label: trimmed, rating, favorite });
                    }}
                >
                    Save
                </button>
                <button
                    type="button"
                    disabled={isSaving || label === null}
                    onClick={() => {
                        setText("");
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
