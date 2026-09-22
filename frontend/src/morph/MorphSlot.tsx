import type { ReactElement } from "react";

import { useLayoutMode } from "../layout/useLayoutMode";
import { samplePreview, useAudioPreview } from "../samples/useAudioPreview";
import { useSamplePreview } from "../samples/useSamplePreview";
import { classNames } from "../shared/classNames";
import { shortHash } from "../shared/format";
import { hintFor } from "../shared/hints";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useSelectionStore } from "../workspace/selectionStore";
import { END_LETTERS, type MorphEnd, useMorphStore } from "./morphStore";
import { useEndpoint } from "./useEndpoint";

interface MorphSlotProps {
    readonly end: MorphEnd;
    /** The sample this end holds, or `null` while it waits for one. */
    readonly hash: string | null;
}

interface ChosenEndProps {
    readonly end: MorphEnd;
    readonly hash: string;
}

interface EmptyEndProps {
    readonly end: MorphEnd;
}

/** A sample's name as the catalog states it, or `null` until it has answered. */
function useSampleName(hash: string): string | null {
    const preview = useSamplePreview(hash);
    return preview.status === "success" ? preview.data.display_name : null;
}

/** The sample as a screen reader hears it: its name, the unnamed label, or the short hash until the catalog answers. */
function spokenNameOf(hash: string, name: string | null): string {
    if (name === null) {
        return shortHash(hash);
    }
    return name === "" ? UNNAMED_SAMPLE_LABEL : name;
}

function Letter({ end }: EmptyEndProps): ReactElement {
    return <span className="morph-slot-letter mono">{END_LETTERS[end]}</span>;
}

/** The end as chosen: its name on the button that plays it and selects the slot, and the × that lets it go. */
function ChosenEnd({ end, hash }: ChosenEndProps): ReactElement {
    const name = useSampleName(hash);
    const reading = useEndpoint(hash);
    const selected = useMorphStore((state) => state.selectedEnd === end);
    const toggleSelectedEnd = useMorphStore((state) => state.toggleSelectedEnd);
    const clearEnd = useMorphStore((state) => state.clearEnd);
    const highlightEntity = useSelectionStore((state) => state.highlightEntity);
    const { play } = useAudioPreview();
    const letter = END_LETTERS[end];

    function handleClick(): void {
        play(samplePreview(hash, reading.rateHz));
        highlightEntity({ kind: "sample", hash });
        toggleSelectedEnd(end);
    }

    return (
        <div className={classNames("morph-slot", selected && "is-selected")} data-end={end}>
            <button
                type="button"
                className="morph-slot-main"
                aria-label={`${letter}: ${spokenNameOf(hash, name)}`}
                aria-pressed={selected}
                onClick={handleClick}
            >
                <Letter end={end} />
                <span className="morph-slot-name">
                    {name === null ? (
                        <span className="mono">{shortHash(hash)}</span>
                    ) : (
                        <OptionalLabel value={name} placeholder={UNNAMED_SAMPLE_LABEL} />
                    )}
                </span>
            </button>
            <button
                type="button"
                className="morph-slot-clear"
                aria-label={`Clear ${letter}`}
                onClick={() => {
                    clearEnd(end);
                }}
            >
                ×
            </button>
        </div>
    );
}

/** An end still waiting for a sample, which says what to do next once it is selected. */
function EmptyEnd({ end }: EmptyEndProps): ReactElement {
    const { input } = useLayoutMode();
    const selected = useMorphStore((state) => state.selectedEnd === end);
    const toggleSelectedEnd = useMorphStore((state) => state.toggleSelectedEnd);
    const hint = hintFor(selected ? "morphSlotSelected" : "morphSlotIdle", input);

    return (
        <div className={classNames("morph-slot morph-slot-empty", selected && "is-selected")} data-end={end}>
            <button
                type="button"
                className="morph-slot-main"
                aria-label={`${END_LETTERS[end]}: ${hint}`}
                aria-pressed={selected}
                onClick={() => {
                    toggleSelectedEnd(end);
                }}
            >
                <Letter end={end} />
                <span className="morph-slot-name">{hint}</span>
            </button>
        </div>
    );
}

/**
 * One end of the morph pair as the strip shows it. Tapping the slot selects it: a chosen end plays
 * and is taken in hand, and every sample tapped next, in a list or on the cloud, becomes this end
 * until the slot is tapped again or the other one is selected.
 */
export function MorphSlot({ end, hash }: MorphSlotProps): ReactElement {
    return hash === null ? <EmptyEnd end={end} /> : <ChosenEnd end={end} hash={hash} />;
}
