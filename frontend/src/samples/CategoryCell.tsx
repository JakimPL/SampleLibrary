import type { ReactElement } from "react";
import { useState } from "react";

import type { SampleSummary } from "../api/samples";
import { CategoryBadge } from "./CategoryBadge";
import { LabelField } from "./LabelField";

interface CategoryCellProps {
    readonly sample: SampleSummary;
    readonly label: string | null;
    readonly onCommit: (label: string | null) => void;
}

/**
 * What a sample is, as a listing shows it and as a person changes it.
 *
 * The badge turns into a field on a click, so naming a sample takes a click and a word from
 * wherever it is listed. Emptying the field takes the hand label back and leaves what the listening
 * model heard showing, which is what makes a wrong category one gesture to correct and one to undo.
 */
export function CategoryCell({ sample, label, onCommit }: CategoryCellProps): ReactElement {
    const [isEditing, setIsEditing] = useState(false);

    if (isEditing) {
        return (
            <LabelField
                label={label}
                onCommit={onCommit}
                onLeave={() => {
                    setIsEditing(false);
                }}
                takesFocus
            />
        );
    }

    return (
        <button
            type="button"
            className="category-cell-button"
            aria-label="Edit category"
            onClick={() => {
                setIsEditing(true);
            }}
        >
            <CategoryBadge sampleHash={sample.hash} category={sample.suggested_label} handLabel={sample.hand_label} />
        </button>
    );
}
