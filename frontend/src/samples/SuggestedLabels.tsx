import type { ReactElement } from "react";

import type { AnnotationScope } from "../api/curation";
import type { SampleDetail } from "../api/samples";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { holdsTag, withTag } from "./labelText";
import { useAnnotationWriter } from "./useAnnotationWriter";

const SCORE_DECIMAL_PLACES = 2;

export const NO_SUGGESTIONS = "No suggestions yet — a scoring of the listening model writes them.";

interface SuggestedLabelsProps {
    readonly sample: SampleDetail;
    /** How far a click reaches, the same reach the annotation editor's own gestures have. */
    readonly scope: AnnotationScope;
}

/**
 * What the listening model hears this sample as, each suggestion a click away from the hand label.
 *
 * A click appends the tag to the wording the sample carries, through the one write path every
 * annotation gesture takes, so the badge, the row and the cloud follow at once; the write reaches
 * as far as the editor's near-duplicates checkbox says and changes the label alone. A tag the label
 * already holds shows as taken.
 */
export function SuggestedLabels({ sample, scope }: SuggestedLabelsProps): ReactElement {
    const current = useSampleAnnotation(sample.hash, decisionsOf(sample));
    const { change, message } = useAnnotationWriter(sample.hash, scope);
    const label = current?.label ?? null;

    if (sample.suggestions.length === 0) {
        return <p className="placeholder-box">{NO_SUGGESTIONS}</p>;
    }

    return (
        <div className="suggested-labels">
            <div className="suggested-labels-row" role="group" aria-label="Suggested labels">
                {sample.suggestions.map((suggestion) => {
                    const taken = holdsTag(label, suggestion.label);
                    return (
                        <button
                            key={suggestion.label}
                            type="button"
                            className="badge badge-suggestion"
                            aria-pressed={taken}
                            disabled={taken}
                            onClick={() => {
                                change({ label: withTag(label, suggestion.label) });
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
