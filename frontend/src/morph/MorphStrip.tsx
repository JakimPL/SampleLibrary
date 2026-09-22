import type { ChangeEvent, ReactElement } from "react";
import { useId, useRef } from "react";

import { samplePreview, useAudioPreview } from "../samples/useAudioPreview";
import { morphAnchorOf, useSelectionStore } from "../workspace/selectionStore";
import { MorphDistance } from "./MorphDistance";
import { END_LETTERS, MorphSlot } from "./MorphSlot";
import { type MorphEnd, useMorphStore, WEIGHT_STEP } from "./morphStore";
import { useMorphStripStore } from "./morphStripStore";
import { MorphWaveform } from "./MorphWaveform";
import { type EndpointReading, useEndpoint } from "./useEndpoint";
import { type MorphPlayback, useMorphPlayback } from "./useMorphPlayback";
import type { MorphStatus } from "./useMorphStatus";

const WEIGHT_DECIMAL_PLACES = 2;
const PERCENT_OF_A_SHARE = 100;
const THUMB_CENTER_SHARE = 0.5;
const OFFLINE_NOTICE = "Morphing is offline.";

/** Where the readout stands over the track: on the thumb's own center, whose travel the thumb's width shortens at either end. */
function readoutOffset(weight: number): string {
    const share = String(weight * PERCENT_OF_A_SHARE);
    const correction = `(${String(THUMB_CENTER_SHARE)} - ${String(weight)}) * var(--range-thumb-size)`;
    return `calc(${share}% + ${correction})`;
}

interface EndPlayProps {
    readonly end: MorphEnd;
    readonly hash: string;
    readonly reading: EndpointReading;
}

/** The original at one end, played at the rate it is heard at. */
function EndPlay({ end, hash, reading }: EndPlayProps): ReactElement {
    const { play, playingKey } = useAudioPreview();
    return (
        <button
            type="button"
            className="morph-strip-tool"
            aria-label={`Play ${END_LETTERS[end]}`}
            aria-pressed={playingKey === hash}
            onClick={() => {
                play(samplePreview(hash, reading.rateHz));
            }}
        >
            ▶
        </button>
    );
}

interface OfflineNoticeProps {
    readonly status: MorphStatus;
}

function OfflineNotice({ status }: OfflineNoticeProps): ReactElement | null {
    if (status.state.status === "loading" || status.available) {
        return null;
    }
    return (
        <p className="panel-status morph-offline" role="status">
            <span>{OFFLINE_NOTICE}</span>
            <button type="button" onClick={status.refresh}>
                Check again
            </button>
        </p>
    );
}

interface MorphBodyProps {
    readonly id: string;
    readonly first: string;
    readonly second: string;
    readonly playback: MorphPlayback;
}

/** The slider between the two originals, the distance between them, and the morph drawn over their traces. */
function MorphBody({ id, first, second, playback }: MorphBodyProps): ReactElement {
    const weight = useMorphStore((state) => state.weight);
    const renderedWeight = useMorphStore((state) => state.renderedWeight);
    const setWeight = useMorphStore((state) => state.setWeight);
    const firstReading = useEndpoint(first);
    const secondReading = useEndpoint(second);
    const movedRef = useRef(false);

    function handleChange(event: ChangeEvent<HTMLInputElement>): void {
        setWeight(Number(event.target.value));
        movedRef.current = true;
    }

    // A pointer or a key let go with the weight where it was, such as a Tab moving focus, asks for nothing.
    function handleRelease(): void {
        if (!movedRef.current) {
            return;
        }
        movedRef.current = false;
        playback.hearCurrentPoint();
    }

    return (
        <div className="morph-strip-body" id={id}>
            <div className="morph-weight">
                <EndPlay end="first" hash={first} reading={firstReading} />
                <div className="morph-weight-track">
                    <span className="morph-readout mono" style={{ left: readoutOffset(weight) }}>
                        {weight.toFixed(WEIGHT_DECIMAL_PLACES)}
                    </span>
                    <input
                        type="range"
                        min={0}
                        max={1}
                        step={WEIGHT_STEP}
                        value={weight}
                        aria-label="Point along the morph"
                        onChange={handleChange}
                        onPointerUp={handleRelease}
                        onKeyUp={handleRelease}
                    />
                </div>
                <EndPlay end="second" hash={second} reading={secondReading} />
            </div>
            <MorphDistance first={first} second={second} />
            <MorphWaveform
                first={first}
                second={second}
                firstReading={firstReading}
                secondReading={secondReading}
                renderedWeight={renderedWeight}
                available={playback.status.available}
            />
        </div>
    );
}

/**
 * The morph along the bottom of the cloud: two slots naming the ends of the pair, or offering the
 * sample in hand for them, and once both are chosen the weight, a play button for the point it
 * names and a chevron opening the slider, the distance and the waveform. The strip stands in every
 * state, so filling the pair changes what it says and leaves the cloud its room. Letting the
 * slider go sounds the render through the shared preview element, the way the marker on the cloud
 * does, and the waveform draws whichever point was let go last.
 */
export function MorphStrip(): ReactElement {
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const weight = useMorphStore((state) => state.weight);
    const swap = useMorphStore((state) => state.swap);
    const inHand = useSelectionStore(morphAnchorOf);
    const expanded = useMorphStripStore((state) => state.expanded);
    const toggleExpanded = useMorphStripStore((state) => state.toggleExpanded);
    const playback = useMorphPlayback();
    const bodyId = useId();
    const pair = first !== null && second !== null ? { first, second } : null;

    return (
        <section className="morph-strip" aria-label="Morph">
            <div className="morph-strip-row">
                <MorphSlot end="first" hash={first} otherHash={second} inHand={inHand} />
                <button
                    type="button"
                    className="morph-strip-tool"
                    aria-label="Swap the two ends"
                    disabled={first === null && second === null}
                    onClick={swap}
                >
                    ⇄
                </button>
                <MorphSlot end="second" hash={second} otherHash={first} inHand={inHand} />
                {pair !== null && (
                    <>
                        <span className="morph-strip-readout mono">{weight.toFixed(WEIGHT_DECIMAL_PLACES)}</span>
                        <button
                            type="button"
                            className="morph-strip-tool morph-strip-hear"
                            aria-label="Play the morph at this weight"
                            disabled={!playback.status.available}
                            onClick={playback.hearCurrentPoint}
                        >
                            ▶
                        </button>
                        <button
                            type="button"
                            className="morph-strip-tool morph-strip-expand"
                            aria-label={expanded ? "Hide the morph waveform" : "Show the morph waveform"}
                            aria-expanded={expanded}
                            aria-controls={bodyId}
                            onClick={toggleExpanded}
                        >
                            {expanded ? "⌄" : "⌃"}
                        </button>
                    </>
                )}
            </div>
            {pair !== null && expanded && (
                <MorphBody id={bodyId} first={pair.first} second={pair.second} playback={playback} />
            )}
            {pair !== null && <OfflineNotice status={playback.status} />}
        </section>
    );
}
