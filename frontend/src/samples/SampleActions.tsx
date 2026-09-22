import type { ReactElement } from "react";

import { useMorphStore } from "../morph/morphStore";
import { samplePreview, useAudioPreview } from "./useAudioPreview";

interface SampleActionsProps {
    readonly sampleHash: string;
    readonly playbackRateHz: number | null;
}

const IS_FIRST_LABEL = "This is A";
const IS_SECOND_LABEL = "This is B";
const FROM_HERE_LABEL = "Morph from here";
const TO_HERE_LABEL = "Morph to here";

/**
 * What a person can do with the sample in front of them by name: play it, and make it either end
 * of the morph pair, the same pair the cloud's gestures and a Shift-click fill. A button whose end
 * the sample already holds says so and rests.
 */
export function SampleActions({ sampleHash, playbackRateHz }: SampleActionsProps): ReactElement {
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const setFirst = useMorphStore((state) => state.setFirst);
    const setSecond = useMorphStore((state) => state.setSecond);
    const { play } = useAudioPreview();
    const isFirst = first === sampleHash;
    const isSecond = second === sampleHash;

    return (
        <div className="sample-actions" role="group" aria-label="Sample actions">
            <button
                type="button"
                onClick={() => {
                    play(samplePreview(sampleHash, playbackRateHz));
                }}
            >
                Play
            </button>
            <button
                type="button"
                disabled={isFirst}
                onClick={() => {
                    setFirst(sampleHash);
                }}
            >
                {isFirst ? IS_FIRST_LABEL : FROM_HERE_LABEL}
            </button>
            <button
                type="button"
                disabled={isSecond}
                onClick={() => {
                    setSecond(sampleHash);
                }}
            >
                {isSecond ? IS_SECOND_LABEL : TO_HERE_LABEL}
            </button>
        </div>
    );
}
