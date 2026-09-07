import { type ReactElement, useCallback, useState } from "react";

import { clearSampleLabel, getLabelVocabulary, type LabelsWritten, setSampleLabel } from "../api/curation";
import type { SampleDetail } from "../api/samples";
import { describeError } from "../shared/fetchState";
import { invalidateRequest } from "../shared/requestCache";
import { useFetch } from "../shared/useFetch";
import { useHandLabel, useLabelStore } from "./labelStore";
import { sampleDetailCacheKey } from "./useSampleDetail";
import { sampleHoverCacheKey } from "./useSampleHoverPreview";

const VOCABULARY_CACHE_KEY = "label-vocabulary";
const VOCABULARY_LIST_ID = "sample-label-vocabulary";
const SMALLEST_GROUP = 1;

interface LabelEditorProps {
    readonly sample: SampleDetail;
}

function forgetCachedSamples(sampleHashes: readonly string[]): void {
    for (const sampleHash of sampleHashes) {
        invalidateRequest(sampleDetailCacheKey(sampleHash));
        invalidateRequest(sampleHoverCacheKey(sampleHash));
    }
}

/**
 * Where a person says what a sample actually is.
 *
 * The wording is free text, and the list of what has already been used is offered back rather than
 * enforced, so one vocabulary settles by habit instead of by a schema nobody has designed yet.
 * Where the sample has near-duplicates the same decision reaches all of them by default, which is
 * how the listing already groups them; each one is recorded on its own, so the group boundary
 * moving later leaves every decision standing.
 */
export function LabelEditor({ sample }: LabelEditorProps): ReactElement {
    const currentLabel = useHandLabel(sample.hash, sample.hand_label);
    const applyLabel = useLabelStore((state) => state.applyLabel);
    const vocabulary = useFetch(getLabelVocabulary, [], VOCABULARY_CACHE_KEY);
    const [text, setText] = useState(currentLabel ?? "");
    const [reachesGroup, setReachesGroup] = useState(sample.equivalence_member_count > SMALLEST_GROUP);
    const [isSaving, setIsSaving] = useState(false);
    const [message, setMessage] = useState<string | null>(null);

    const run = useCallback(
        (operation: Promise<LabelsWritten>): void => {
            setIsSaving(true);
            setMessage(null);
            operation
                .then((written) => {
                    applyLabel(written.sample_hashes, written.label);
                    forgetCachedSamples(written.sample_hashes);
                    invalidateRequest(VOCABULARY_CACHE_KEY);
                })
                .catch((error: unknown) => {
                    setMessage(describeError(error));
                })
                .finally(() => {
                    setIsSaving(false);
                });
        },
        [applyLabel],
    );

    const scope = reachesGroup ? "equivalence_class" : "sample";
    const trimmed = text.trim();

    return (
        <div className="label-editor">
            <input
                className="label-editor-input"
                type="text"
                list={VOCABULARY_LIST_ID}
                placeholder="What is this sample?"
                value={text}
                aria-label="Hand label"
                onChange={(event) => {
                    setText(event.target.value);
                }}
            />
            <datalist id={VOCABULARY_LIST_ID}>
                {vocabulary.status === "success" &&
                    vocabulary.data.map((known) => <option key={known} value={known} />)}
            </datalist>
            <button
                type="button"
                disabled={isSaving || trimmed === ""}
                onClick={() => {
                    run(setSampleLabel(sample.hash, trimmed, scope));
                }}
            >
                Save
            </button>
            <button
                type="button"
                disabled={isSaving || currentLabel === null}
                onClick={() => {
                    setText("");
                    run(clearSampleLabel(sample.hash, scope));
                }}
            >
                Clear
            </button>
            {sample.equivalence_member_count > SMALLEST_GROUP && (
                <label className="label-editor-scope">
                    <input
                        type="checkbox"
                        checked={reachesGroup}
                        onChange={(event) => {
                            setReachesGroup(event.target.checked);
                        }}
                    />
                    Apply to all {sample.equivalence_member_count} near-duplicates
                </label>
            )}
            {message !== null && <p className="label-editor-message">{message}</p>}
        </div>
    );
}
