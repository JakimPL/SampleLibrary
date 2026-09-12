import type { ChangeEvent, ReactElement } from "react";
import { Link } from "react-router-dom";

import { morphPreview } from "../../morph/morphPreview";
import { morphPlaybackRateHz } from "../../morph/morphRate";
import { useMorphStore, WEIGHT_STEP } from "../../morph/morphStore";
import { type MorphStatus, useMorphStatus } from "../../morph/useMorphStatus";
import { PlayButton } from "../../samples/PlayButton";
import { useAudioPreview } from "../../samples/useAudioPreview";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { classNames } from "../../shared/classNames";
import { shortHash } from "../../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../../shared/labels";
import { OptionalLabel } from "../../shared/OptionalLabel";
import { useSelectionStore } from "../selectionStore";
import { useEntityRowInteractions } from "../useEntityRowInteractions";

const WEIGHT_DECIMAL_PLACES = 2;
const NO_PAIR_HINT =
    "No morph pair yet — in the Cloud, drag from one sample to another with the right mouse button, or click one and right-click another.";
const OFFLINE_NOTICE = "Morphing is offline: the inference service is not reachable.";
const RATE_UNKNOWN = "rate unknown";

interface EndpointReading {
    readonly name: string;
    readonly rateHz: number | null;
}

function useEndpoint(sampleHash: string): EndpointReading {
    const state = useSampleDetail(sampleHash);
    if (state.status !== "success") {
        return { name: "", rateHz: null };
    }
    return { name: state.data.sample.display_name, rateHz: state.data.sample.playback_rate_hz };
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
    const playOnRelease = useMorphStore((state) => state.playOnRelease);
    const setWeight = useMorphStore((state) => state.setWeight);
    const setPlayOnRelease = useMorphStore((state) => state.setPlayOnRelease);
    const swap = useMorphStore((state) => state.swap);
    const clear = useMorphStore((state) => state.clear);
    const firstReading = useEndpoint(first);
    const secondReading = useEndpoint(second);
    const { play, playingKey } = useAudioPreview();
    const source = morphPreview(first, second, weight, firstReading.rateHz, secondReading.rateHz);
    const rateHz = morphPlaybackRateHz(firstReading.rateHz, secondReading.rateHz, weight);

    function playMorph(): void {
        if (status.available) {
            play(source);
        }
    }

    function commitWeight(): void {
        if (playOnRelease) {
            playMorph();
        }
    }

    return (
        <>
            <div className="morph-endpoints">
                <MorphEndpoint sampleHash={first} reading={firstReading} />
                <button type="button" onClick={swap} aria-label="Swap the two ends">
                    ⇄
                </button>
                <MorphEndpoint sampleHash={second} reading={secondReading} />
            </div>
            <div className="morph-weight">
                <span className="mono cell-muted">A</span>
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
                <span className="mono cell-muted">B</span>
            </div>
            <div className="morph-actions">
                <span className="morph-readout mono">
                    {weight.toFixed(WEIGHT_DECIMAL_PLACES)} ·{" "}
                    {rateHz === null ? RATE_UNKNOWN : `${String(Math.round(rateHz))} Hz`}
                </span>
                <button
                    type="button"
                    onClick={playMorph}
                    disabled={!status.available}
                    aria-pressed={playingKey === source.key}
                >
                    ▶ Play morph
                </button>
                <button type="button" onClick={clear}>
                    Clear
                </button>
                <label>
                    <input
                        type="checkbox"
                        checked={playOnRelease}
                        onChange={(event: ChangeEvent<HTMLInputElement>) => {
                            setPlayOnRelease(event.target.checked);
                        }}
                    />
                    Play on release
                </label>
            </div>
        </>
    );
}

/**
 * Two samples, a weight between them, and the morph that weight names: the pair comes from the
 * cloud's right-button gesture or from the shell's own focus and comparison slots, the slider mirrors the
 * marker on the cloud, and Play sounds the render through the shared preview element. The panel
 * says so when no inference process answers, and offers to look again.
 */
export function MorphPanel(): ReactElement {
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const setPair = useMorphStore((state) => state.setPair);
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);
    const comparisonSampleHash = useSelectionStore((state) => state.comparisonSampleHash);
    const status = useMorphStatus();
    const selectionReady = focusedSampleHash !== null && comparisonSampleHash !== null;

    return (
        <div className="morph-panel">
            {first !== null && second !== null ? (
                <MorphPair first={first} second={second} status={status} />
            ) : (
                <p className="no-selection">{NO_PAIR_HINT}</p>
            )}
            <div className="morph-actions">
                <button
                    type="button"
                    disabled={!selectionReady}
                    onClick={() => {
                        setPair(focusedSampleHash, comparisonSampleHash);
                    }}
                >
                    Use selection
                </button>
            </div>
            <OfflineNotice status={status} />
        </div>
    );
}
