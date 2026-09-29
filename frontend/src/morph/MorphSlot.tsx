import type { ReactElement, ReactNode } from "react";

import { SampleName } from "../samples/SampleName";
import { samplePreview, useAudioPreview } from "../samples/useAudioPreview";
import { spokenNameOf, useSampleName } from "../samples/useSampleName";
import { classNames } from "../shared/classNames";
import { useSelectionStore } from "../workspace/selectionStore";
import { END_LETTERS, type MorphEnd, useMorphStore } from "./morphStore";
import { useEndpoint } from "./useEndpoint";

const EMPTY_READING = "empty";

interface MorphSlotProps {
    readonly end: MorphEnd;
    /** The sample this end holds, or `null` before its first. */
    readonly hash: string | null;
}

interface ChosenEndProps {
    readonly end: MorphEnd;
    readonly hash: string;
}

interface EmptyEndProps {
    readonly end: MorphEnd;
}

interface SlotButtonProps {
    readonly end: MorphEnd;
    /** What the end says to a screen reader after its letter. */
    readonly spoken: string;
    readonly empty: boolean;
    readonly onClick: () => void;
    readonly children: ReactNode;
}

/** The button every slot is: the end's letter and what it holds, pressed while the end is selected. */
function SlotButton({ end, spoken, empty, onClick, children }: SlotButtonProps): ReactElement {
    const selected = useMorphStore((state) => state.selectedEnd === end);
    const letter = END_LETTERS[end];

    return (
        <button
            type="button"
            className={classNames("morph-slot", empty && "morph-slot-empty", selected && "is-selected")}
            aria-label={`${letter}: ${spoken}`}
            aria-pressed={selected}
            onClick={onClick}
        >
            <span className="morph-slot-letter mono">{letter}</span>
            <span className="morph-slot-name">{children}</span>
        </button>
    );
}

/** The end as chosen: a tap plays its sample at the sample's own rate, takes it in hand and selects the end. */
function ChosenEnd({ end, hash }: ChosenEndProps): ReactElement {
    const name = useSampleName(hash);
    const reading = useEndpoint(hash);
    const selectEnd = useMorphStore((state) => state.selectEnd);
    const highlightEntity = useSelectionStore((state) => state.highlightEntity);
    const { play } = useAudioPreview();

    function handleClick(): void {
        play(samplePreview(hash, reading.rateHz));
        highlightEntity({ kind: "sample", hash });
        selectEnd(end);
    }

    return (
        <SlotButton end={end} spoken={spokenNameOf(hash, name)} empty={false} onClick={handleClick}>
            <SampleName hash={hash} name={name} />
        </SlotButton>
    );
}

function EmptyEnd({ end }: EmptyEndProps): ReactElement {
    const selectEnd = useMorphStore((state) => state.selectEnd);

    return (
        <SlotButton
            end={end}
            spoken={EMPTY_READING}
            empty
            onClick={() => {
                selectEnd(end);
            }}
        >
            {EMPTY_READING}
        </SlotButton>
    );
}

/**
 * One end of the morph pair as the strip shows it. The selected end takes every sample picked
 * next, in a list or on the cloud; a tap on a slot selects its end.
 */
export function MorphSlot({ end, hash }: MorphSlotProps): ReactElement {
    return hash === null ? <EmptyEnd end={end} /> : <ChosenEnd end={end} hash={hash} />;
}
