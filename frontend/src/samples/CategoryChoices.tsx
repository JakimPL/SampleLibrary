import type { ReactElement } from "react";

import type { AnnotationScope } from "../api/curation";
import type { SampleDetail } from "../api/samples";
import { decisionsOf, useSampleAnnotation } from "./annotationStore";
import { assertsTag, withTag } from "./labelText";
import { useAnnotationWriter } from "./useAnnotationWriter";

const SCORE_DECIMAL_PLACES = 2;

export const NO_CATEGORIES = "No categories yet — a scoring of the listening model writes them.";

interface CategoryChoicesProps {
    readonly sample: SampleDetail;
    /** How far a click reaches, the same reach the annotation editor's own gestures have. */
    readonly scope: AnnotationScope;
}

/**
 * The categories the listening model hears this sample as, closest first, each a click away from the hand label.
 *
 * A click writes the category into the wording the sample carries, through the one write path
 * every annotation gesture takes, so the badge, the row and the cloud follow at once; the write
 * reaches as far as the editor's near-duplicates checkbox says and changes the label alone. A
 * category the label already asserts shows as taken, a broad one included once a specification
 * under it is written; a category more detailed than one the label names takes its place there.
 */
export function CategoryChoices({ sample, scope }: CategoryChoicesProps): ReactElement {
    const current = useSampleAnnotation(sample.hash, decisionsOf(sample));
    const { change, message } = useAnnotationWriter(sample.hash, scope);
    const label = current?.label ?? null;

    if (sample.categories.length === 0) {
        return <p className="placeholder-box">{NO_CATEGORIES}</p>;
    }

    return (
        <div className="category-choices">
            <div className="category-choices-row" role="group" aria-label="Categories">
                {sample.categories.map((category) => {
                    const taken = assertsTag(label, category.label);
                    return (
                        <button
                            key={category.label}
                            type="button"
                            className="badge badge-category-choice"
                            aria-pressed={taken}
                            disabled={taken}
                            onClick={() => {
                                change({ label: withTag(label, category.label) });
                            }}
                        >
                            {category.label}
                            <span className="category-score">{category.score.toFixed(SCORE_DECIMAL_PLACES)}</span>
                        </button>
                    );
                })}
            </div>
            {message !== null && <p className="annotation-editor-message">{message}</p>}
        </div>
    );
}
