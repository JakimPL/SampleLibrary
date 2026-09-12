import type { ReactElement } from "react";

import type { SampleDetail } from "../api/samples";
import { defaultScopeFor } from "./AnnotationEditor";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { holdsTag, withTag } from "./labelText";
import { useAnnotationWriter } from "./useAnnotationWriter";

const SCORE_DECIMAL_PLACES = 2;

export const NO_SUGGESTIONS = "No suggestions yet — a scoring of the listening model writes them.";

interface SuggestedLabelsProps {
    readonly sample: SampleDetail;
}

/**
 * What the listening model hears this sample as, each suggestion a click away from the hand label.
 *
 * A click appends the tag to the wording the sample carries, through the one write path every
 * annotation gesture takes, so the badge, the row and the cloud follow at once; the write reaches
 * the sample's near-duplicates the way the editor's own default does. A tag the label already
 * holds shows as taken.
 */
export function SuggestedLabels({ sample }: SuggestedLabelsProps): ReactElement {
    const current = useSampleAnnotation(sample.hash, decisionsOf(sample));
    const { write, isSaving, message } = useAnnotationWriter(sample.hash, defaultScopeFor(sample));
    const label = current?.label ?? null;
    const rating = current?.rating ?? null;
    const favorite = current?.favorite ?? false;

    if (sample.suggested_labels.length === 0) {
        return <p className="placeholder-box">{NO_SUGGESTIONS}</p>;
    }

    return (
        <div className="suggested-labels">
            <div className="suggested-labels-row" role="group" aria-label="Suggested labels">
                {sample.suggested_labels.map((suggestion) => {
                    const taken = holdsTag(label, suggestion.label);
                    return (
                        <button
                            key={suggestion.label}
                            type="button"
                            className="badge badge-suggestion"
                            aria-pressed={taken}
                            disabled={isSaving || taken}
                            onClick={() => {
                                write({ label: withTag(label, suggestion.label), rating, favorite });
                            }}
                        >
                            {suggestion.label}
                            <span className="suggestion-score">{suggestion.score.toFixed(SCORE_DECIMAL_PLACES)}</span>
                        </button>
                    );
                })}
            </div>
            {message !== null && <p className="annotation-editor-message">{message}</p>}
        </div>
    );
}
