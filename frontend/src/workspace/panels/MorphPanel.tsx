import type { ChangeEvent, ReactElement } from "react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { MorphDistance } from "../../morph/MorphDistance";
import { morphPreview } from "../../morph/morphPreview";
import { useMorphStore, WEIGHT_STEP } from "../../morph/morphStore";
import { MorphWaveform } from "../../morph/MorphWaveform";
import { type EndpointReading, useEndpoint } from "../../morph/useEndpoint";
import { type MorphStatus, useMorphStatus } from "../../morph/useMorphStatus";
import { PlayButton } from "../../samples/PlayButton";
import { useAudioPreview } from "../../samples/useAudioPreview";
import { classNames } from "../../shared/classNames";
import { shortHash } from "../../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../../shared/labels";
import { OptionalLabel } from "../../shared/OptionalLabel";
import { useEntityRowInteractions } from "../useEntityRowInteractions";

const WEIGHT_DECIMAL_PLACES = 2;
const PERCENT_OF_A_SHARE = 100;
const THUMB_CENTER_SHARE = 0.5;
/** What the panel asks for while no pair is joined. */
export const NO_PAIR_HINT =
    "Drag a sample from the Cloud to another with the right mouse button, or click one and right-click another.";
const OFFLINE_NOTICE = "Morphing is offline.";

/** Where the readout stands over the track: on the thumb's own center, whose travel the thumb's width shortens at either end. */
function readoutOffset(weight: number): string {
    const share = String(weight * PERCENT_OF_A_SHARE);
    const correction = `(${String(THUMB_CENTER_SHARE)} - ${String(weight)}) * var(--range-thumb-size)`;
    return `calc(${share}% + ${correction})`;
}

interface MorphEndpointProps {
    readonly sampleHash: string;
    readonly reading: EndpointReading;
}

/**
 * One end of the pair: the original one click away at its own rate, and its hash and name as the
 * link every listing row carries, so a click highlights the sample wherever the shell shows it, a
 * Shift-click compares it, and a double-click opens it in the Sample Detail.
 */
function MorphEndpoint({ sampleHash, reading }: MorphEndpointProps): ReactElement {
    const { href, isHighlighted, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "sample",
        hash: sampleHash,
    });
    return (
        <div className="morph-endpoint">
            <PlayButton sampleHash={sampleHash} playbackRateHz={reading.rateHz}>
                ▶
            </PlayButton>
            <Link
                to={href}
                className={classNames("morph-endpoint-identity", isHighlighted && "is-highlighted")}
                onClickCapture={onClick}
                onDoubleClick={onDoubleClick}
            >
                <span className="entity-hash mono">{shortHash(sampleHash)}</span>
                <span className="morph-endpoint-name">
                    <OptionalLabel value={reading.name} placeholder={UNNAMED_SAMPLE_LABEL} />
                </span>
            </Link>
        </div>
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

interface MorphPairProps {
    readonly first: string;
    readonly second: string;
    readonly status: MorphStatus;
}

function MorphPair({ first, second, status }: MorphPairProps): ReactElement {
    const weight = useMorphStore((state) => state.weight);
    const setWeight = useMorphStore((state) => state.setWeight);
    const swap = useMorphStore((state) => state.swap);
    const clear = useMorphStore((state) => state.clear);
    const firstReading = useEndpoint(first);
    const secondReading = useEndpoint(second);
    const { play } = useAudioPreview();
    const [renderedWeight, setRenderedWeight] = useState<number | null>(null);
    const committedWeightRef = useRef(weight);

    // A pointer or a key let go with the weight where it was, such as a Tab moving focus, asks for nothing.
    function commitWeight(): void {
        if (weight === committedWeightRef.current) {
            return;
        }
        committedWeightRef.current = weight;
        if (status.available) {
            setRenderedWeight(weight);
            play(morphPreview(first, second, weight));
        }
    }

    return (
        <>
            <div className="morph-endpoints">
                <MorphEndpoint sampleHash={first} reading={firstReading} />
                <div className="morph-gap">
                    <button type="button" onClick={swap} aria-label="Swap the two ends">
                        ⇄
                    </button>
                    <MorphDistance first={first} second={second} />
                </div>
                <MorphEndpoint sampleHash={second} reading={secondReading} />
                <button type="button" className="morph-clear" onClick={clear} aria-label="Clear the pair">
                    ×
                </button>
            </div>
            <div className="morph-weight">
                <span className="mono cell-muted">A</span>
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
                        aria-label="Morph weight"
                        onChange={(event: ChangeEvent<HTMLInputElement>) => {
                            setWeight(Number(event.target.value));
                        }}
                        onPointerUp={commitWeight}
                        onKeyUp={commitWeight}
                    />
                </div>
                <span className="mono cell-muted">B</span>
            </div>
            <MorphWaveform
                first={first}
                second={second}
                firstReading={firstReading}
                secondReading={secondReading}
                renderedWeight={renderedWeight}
                available={status.available}
            />
        </>
    );
}

/**
 * Two samples, a weight between them, and the morph that weight names: the pair comes from the
 * cloud's right-button gesture or from a Shift-click on a sample row, the slider mirrors the marker
 * on the cloud, and letting the slider go sounds the render through the shared preview element and
 * draws it over the traces of both ends. The panel says so when no inference process answers, and
 * offers to look again.
 *
 * Each pair gets a panel of its own, so the render on screen belongs to the two samples under it
 * and a swap or a fresh join starts from nothing drawn.
 */
export function MorphPanel(): ReactElement {
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const status = useMorphStatus();

    return (
        <div className="morph-panel">
            {first !== null && second !== null ? (
                <MorphPair key={`${first}:${second}`} first={first} second={second} status={status} />
            ) : (
                <p className="no-selection">{NO_PAIR_HINT}</p>
            )}
            <OfflineNotice status={status} />
        </div>
    );
}
