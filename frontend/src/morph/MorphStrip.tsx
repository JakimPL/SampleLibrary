import type { ChangeEvent, ReactElement } from "react";
import { useEffect, useId, useRef } from "react";

import { useLayoutMode } from "../layout/useLayoutMode";
import { FocusedSampleTransport } from "../samples/SampleTransport";
import { Icon } from "../shared/icons/Icon";
import { MorphDistance } from "./MorphDistance";
import { MorphSlot } from "./MorphSlot";
import { END_LETTERS, useMorphStore, WEIGHT_STEP } from "./morphStore";
import { useMorphStripStore } from "./morphStripStore";
import { MorphWaveform } from "./MorphWaveform";
import { useEndpoint } from "./useEndpoint";
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

interface PairProps {
    readonly first: string;
    readonly second: string;
    readonly playback: MorphPlayback;
}

/** The slider between the two ends, and the distance between them where the panel has room for it. */
function MorphSlider({ first, second, playback }: PairProps): ReactElement {
    const weight = useMorphStore((state) => state.weight);
    const setWeight = useMorphStore((state) => state.setWeight);
    const { layout } = useLayoutMode();
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
        <div className="morph-strip-body">
            <div className="morph-weight">
                <span className="mono cell-muted">{END_LETTERS.first}</span>
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
                <span className="mono cell-muted">{END_LETTERS.second}</span>
            </div>
            {layout === "workspace" && <MorphDistance first={first} second={second} />}
        </div>
    );
}

/** The morph drawn over both ends' traces, with the transport that sounds the drawn point again. */
function MorphPairWaveform({ first, second, playback }: PairProps): ReactElement {
    const renderedWeight = useMorphStore((state) => state.renderedWeight);
    const firstReading = useEndpoint(first);
    const secondReading = useEndpoint(second);

    return (
        <MorphWaveform
            first={first}
            second={second}
            firstReading={firstReading}
            secondReading={secondReading}
            renderedWeight={renderedWeight}
            available={playback.status.available}
        />
    );
}

/**
 * The morph along the bottom of the cloud: a slot for each end of the pair, the swap between them
 * and the waveform button, always that one row. Tapping a slot selects it, and the selected end
 * takes every sample tapped next until the slot is tapped again; an empty slot at rest takes the
 * sample in hand outright; × lets an end go and ⇄ swaps the ends. Once both ends are chosen the
 * slider stands under the row, and the waveform button opens a waveform beneath it: the morph
 * drawn over both ends, or a lone chosen end's own player. The morph is drawn at the slider's
 * point as soon as both ends are chosen, unheard, so the ends themselves are heard first; letting
 * the slider go sounds a point through the shared preview element, the way the marker on the
 * cloud does, and the waveform draws whichever point was let go last. The selection lets go when
 * the strip leaves the screen.
 */
export function MorphStrip(): ReactElement {
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const swap = useMorphStore((state) => state.swap);
    const deselectEnd = useMorphStore((state) => state.deselectEnd);
    const expanded = useMorphStripStore((state) => state.expanded);
    const toggleExpanded = useMorphStripStore((state) => state.toggleExpanded);
    const playback = useMorphPlayback();
    const bodyId = useId();
    const pair = first !== null && second !== null ? { first, second } : null;
    const lone = pair === null ? (first ?? second) : null;
    const shown = expanded && (pair !== null || lone !== null);

    useEffect(
        () => (): void => {
            deselectEnd();
        },
        [deselectEnd],
    );

    return (
        <section className="morph-strip" aria-label="Morph">
            <div className="morph-strip-row">
                <MorphSlot end="first" hash={first} />
                <button
                    type="button"
                    className="morph-strip-tool"
                    aria-label="Swap the two ends"
                    disabled={first === null && second === null}
                    onClick={swap}
                >
                    ⇄
                </button>
                <MorphSlot end="second" hash={second} />
                <button
                    type="button"
                    className="morph-strip-tool morph-strip-toggle"
                    aria-label="Waveform"
                    aria-expanded={shown}
                    aria-controls={bodyId}
                    disabled={pair === null && lone === null}
                    onClick={toggleExpanded}
                >
                    <Icon name="waveform" label={null} />
                </button>
            </div>
            {pair !== null && <MorphSlider first={pair.first} second={pair.second} playback={playback} />}
            {shown && pair !== null && (
                <div className="morph-strip-wave" id={bodyId}>
                    <MorphPairWaveform first={pair.first} second={pair.second} playback={playback} />
                </div>
            )}
            {shown && lone !== null && (
                <div className="morph-strip-wave" id={bodyId}>
                    <FocusedSampleTransport sampleHash={lone} />
                </div>
            )}
            {pair !== null && <OfflineNotice status={playback.status} />}
        </section>
    );
}
