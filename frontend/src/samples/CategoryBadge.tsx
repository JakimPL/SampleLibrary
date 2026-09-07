import type { ReactElement } from "react";

import { CATEGORY_LABELS, type SampleCategory } from "./category";
import { useHandLabel } from "./labelStore";

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
    const resolved = useHandLabel(sampleHash, handLabel);
    if (resolved !== null) {
        return <span className="badge badge-hand-label">{resolved}</span>;
    }

    return <span className={`badge badge-category-${category}`}>{CATEGORY_LABELS[category]}</span>;
}
