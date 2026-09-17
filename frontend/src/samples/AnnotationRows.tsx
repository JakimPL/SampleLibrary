import { type ReactElement, useState } from "react";

import type { SampleDetail } from "../api/samples";
import { AnnotationEditor, defaultScopeFor } from "./AnnotationEditor";
import { CategoryChoices } from "./CategoryChoices";

interface AnnotationRowsProps {
    readonly sample: SampleDetail;
}

/**
 * A sample's label, rating and favorite mark, with the categories the listening model hears beneath them.
 *
 * Both answer to one near-duplicates checkbox, so a category clicked right after the box is cleared
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
            <dt>Categories</dt>
            <dd>
                <CategoryChoices sample={sample} scope={scope} />
            </dd>
        </>
    );
}
