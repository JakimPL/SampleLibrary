import type { ReactElement } from "react";
import { useState } from "react";

import type { SampleSummary } from "../api/samples";
import type { InputMode } from "../layout/layoutMode";
import { CategoryBadge } from "./CategoryBadge";
import { LabelField } from "./LabelField";
import { LabelSheet } from "./LabelSheet";

interface CategoryCellProps {
    readonly sample: SampleSummary;
    readonly label: string | null;
    readonly onCommit: (label: string | null) => void;
    readonly input: InputMode;
}

/**
 * What a sample is, as a listing shows it and as a person changes it.
 *
 * The badge turns into a field on a click, so naming a sample takes a click and a word from
 * wherever it is listed; under touch a tap opens the label sheet instead, with the field at a
 * finger's size. Emptying the field takes the hand label back and leaves what the listening
 * model heard showing, which is what makes a wrong category one gesture to correct and one to undo.
 */
export function CategoryCell({ sample, label, onCommit, input }: CategoryCellProps): ReactElement {
    const [isEditing, setIsEditing] = useState(false);

    function leave(): void {
        setIsEditing(false);
    }

    if (isEditing && input === "pointer") {
        return <LabelField label={label} onCommit={onCommit} onLeave={leave} takesFocus />;
    }

    return (
        <>
            <button
                type="button"
                className="category-cell-button"
                aria-label="Edit category"
                onClick={() => {
                    setIsEditing(true);
                }}
            >
                <CategoryBadge sampleHash={sample.hash} category={sample.category} handLabel={sample.hand_label} />
            </button>
            {isEditing && <LabelSheet label={label} onCommit={onCommit} onClose={leave} />}
        </>
    );
}
