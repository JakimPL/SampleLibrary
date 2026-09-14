import { type ReactElement, useState } from "react";

import type { SampleDetail } from "../api/samples";
import { AnnotationEditor, defaultScopeFor } from "./AnnotationEditor";
import { SuggestedLabels } from "./SuggestedLabels";

interface AnnotationRowsProps {
    readonly sample: SampleDetail;
}

/**
 * A sample's label, rating and favorite mark, with the listening model's suggestions beneath them.
 *
 * Both answer to one near-duplicates checkbox, so a suggestion clicked right after the box is cleared
 * reaches this sample alone, the same as a star given in the editor does. Mounted per sample, so the
 * box starts from each sample's own default.
 */
export function AnnotationRows({ sample }: AnnotationRowsProps): ReactElement {
    const [scope, setScope] = useState(defaultScopeFor(sample));

    return (
        <>
            <dt>Label</dt>
            <dd>
                <AnnotationEditor sample={sample} scope={scope} onScopeChange={setScope} />
            </dd>
            <dt>Suggested</dt>
            <dd>
                <SuggestedLabels sample={sample} scope={scope} />
            </dd>
        </>
    );
}
