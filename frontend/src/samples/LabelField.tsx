import type { KeyboardEvent, ReactElement } from "react";
import { useEffect, useId, useRef, useState } from "react";

import { getLabelVocabulary } from "../api/curation";
import { useFetch } from "../shared/useFetch";
import { VOCABULARY_CACHE_KEY } from "./useAnnotationWriter";

const COMMIT_KEY = "Enter";
const REVERT_KEY = "Escape";

interface LabelFieldProps {
    readonly label: string | null;
    readonly isSaving: boolean;
    readonly onCommit: (label: string | null) => void;
    /** Called once the field is done being edited, whether the wording was committed or taken back. */
    readonly onLeave: () => void;
    /** Whether the field opened in answer to a person asking for it, and should hold the cursor. */
    readonly takesFocus: boolean;
}

/**
 * Where a person types what a sample is, wherever they are looking at one.
 *
 * Enter and leaving the field both record the wording, and Escape puts back what was there before:
 * naming a sample is one thought, and a listener working through a library finishes it and moves on
 * rather than reaching for a button. An emptied field takes the label back, which is what leaves the
 * guessed category showing again. The wording already in use is offered as a list, so one vocabulary
 * settles by habit rather than by a schema nobody has designed yet.
 */
export function LabelField({ label, isSaving, onCommit, onLeave, takesFocus }: LabelFieldProps): ReactElement {
    const vocabularyListId = useId();
    const vocabulary = useFetch(getLabelVocabulary, [], { cacheKey: VOCABULARY_CACHE_KEY });
    const [text, setText] = useState(label ?? "");
    const inputRef = useRef<HTMLInputElement | null>(null);

    // Focus follows `takesFocus`, so the cursor lands only in the field a click opened.
    useEffect(() => {
        if (takesFocus) {
            inputRef.current?.focus();
        }
    }, [takesFocus]);

    function commit(): void {
        const trimmed = text.trim();
        const next = trimmed === "" ? null : trimmed;
        if (next !== label) {
            onCommit(next);
        }

        onLeave();
    }

    function handleKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
        if (event.key === COMMIT_KEY) {
            commit();
        }
        if (event.key === REVERT_KEY) {
            setText(label ?? "");
            onLeave();
        }
    }

    return (
        <>
            <input
                ref={inputRef}
                className="annotation-editor-input"
                type="text"
                list={vocabularyListId}
                placeholder="Label (e.g. BASS)"
                value={text}
                aria-label="Hand label"
                disabled={isSaving}
                onChange={(event) => {
                    setText(event.target.value);
                }}
                onKeyDown={handleKeyDown}
                onBlur={commit}
                onDoubleClick={(event) => {
                    event.stopPropagation();
                }}
            />
            <datalist id={vocabularyListId}>
                {vocabulary.status === "success" &&
                    vocabulary.data.map((known) => <option key={known} value={known} />)}
            </datalist>
        </>
    );
}
