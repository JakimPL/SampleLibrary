import type { ReactElement } from "react";

import { UNLABELED_SAMPLE_LABEL } from "../shared/labels";
import { useSampleAnnotation } from "./annotationStore";
import { useSuggestionColor } from "./useSuggestionColor";

interface CategoryBadgeProps {
    readonly sampleHash: string;
    readonly suggestedLabel: string | null;
    readonly handLabel: string | null;
}

/**
 * The badge naming what a sample is, wherever a sample's name appears.
 *
 * A hand label wins, being what a person actually decided, and wears a solid style of its own. In
 * its place stands what the listening model heard first, in the dashed style a machine-made
 * statement takes, with a swatch in its category's color; a sample neither has named reads as
 * unlabeled. The label set in this session counts at once, so a badge follows an edit the moment
 * it is made.
 */
export function CategoryBadge({ sampleHash, suggestedLabel, handLabel }: CategoryBadgeProps): ReactElement {
    const annotation = useSampleAnnotation(sampleHash, { label: handLabel, rating: null, favorite: false });
    const colorOf = useSuggestionColor();
    const resolved = annotation?.label ?? null;
    if (resolved !== null) {
        return <span className="badge badge-hand-label">{resolved}</span>;
    }
    if (suggestedLabel === null) {
        return <span className="badge badge-unlabeled">{UNLABELED_SAMPLE_LABEL}</span>;
    }

    const color = colorOf(suggestedLabel);
    return (
        <span className="badge badge-category">
            {color !== null && <span className="badge-swatch" style={{ background: color }} aria-hidden />}
            {suggestedLabel}
        </span>
    );
}
