import type { ReactElement } from "react";

import { useSampleAnnotation } from "./annotationStore";
import { CATEGORY_LABELS, type SampleCategory } from "./category";

interface CategoryBadgeProps {
    readonly sampleHash: string;
    readonly category: SampleCategory;
    readonly handLabel: string | null;
}

/**
 * The badge naming what a sample is, wherever a sample's name appears.
 *
 * A hand label wins over the guessed category, being what a person actually decided. The fourteen
 * guessed roles each own a fixed hue, which a free-text label has no place in, so a hand label
 * wears one style of its own and reads as the different kind of statement it is.
 */
export function CategoryBadge({ sampleHash, category, handLabel }: CategoryBadgeProps): ReactElement {
    const annotation = useSampleAnnotation(sampleHash, { label: handLabel, rating: null, favorite: false });
    const resolved = annotation?.label ?? null;
    if (resolved !== null) {
        return <span className="badge badge-hand-label">{resolved}</span>;
    }

    return <span className={`badge badge-category-${category}`}>{CATEGORY_LABELS[category]}</span>;
}
