import type { ChangeEvent, ReactElement } from "react";
import { useEffect } from "react";

import { sampleAudioUrl } from "../api/samples";
import { useLayoutMode } from "../layout/useLayoutMode";
import { DownloadLink } from "../shared/DownloadLink";
import { formatDuration } from "../shared/format";
import { useAudioPreview } from "./useAudioPreview";
import { useWaveformPlayer } from "./useWaveformPlayer";
import { NO_TRACES, type WaveformNotice, WaveformView } from "./WaveformView";
import { WavePanel } from "./WavePanel";

export interface RateOption {
    readonly rateHz: number;
    readonly eventCount: number;
}

interface WaveformPlayerProps {
    readonly sampleHash: string;
    /** The name a saved copy of this sample takes, ending in its own extension. */
    readonly fileName: string;
    readonly rateHz: number;
    readonly rateOptions: readonly RateOption[];
    readonly onRateChange: (rateHz: number) => void;
}

const AUDIO_UNAVAILABLE_NOTICE: WaveformNotice = {
    text: "Audio unavailable: the file this sample is read from may be gone or changed since its scan.",
    failed: true,
};

function describeRateOption(option: RateOption): string {
    const timeWord = option.eventCount === 1 ? "time" : "times";
    return `${String(option.rateHz)} Hz · played ${String(option.eventCount)} ${timeWord}`;
}

/**
 * The full player of one sample: its decoded waveform over a transport, the rate it is heard at,
 * and a way to save it. On a phone it is one row instead: the play button and the file to save at
 * either side of the waveform, the time in the frame's corner, the sample heard at the rate the
 * library plays it. It keeps to one voice with the shared preview element: playing here silences
 * a preview, and a preview starting anywhere pauses this player.
 */
export function WaveformPlayer({
    sampleHash,
    fileName,
    rateHz,
    rateOptions,
    onRateChange,
}: WaveformPlayerProps): ReactElement {
    const player = useWaveformPlayer(sampleAudioUrl(sampleHash), rateHz);
    const { playingKey, stop } = useAudioPreview();
    const compact = useLayoutMode().layout === "phone";

    useEffect(() => {
        if (playingKey !== null) {
            player.pause();
        }
        // The pause reaches the live wavesurfer instance through a ref, so the player object itself is no dependency.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [playingKey]);

    function handleTogglePlay(): void {
        if (player.isPlaying) {
            player.pause();
        } else {
            stop();
            player.play();
        }
    }

    function handleRateChange(event: ChangeEvent<HTMLSelectElement>): void {
        const nextRateHz = Number(event.target.value);
        onRateChange(nextRateHz);
        player.setRateHz(nextRateHz);
    }

    const readout = `${formatDuration(player.currentTimeSeconds)} / ${formatDuration(player.durationSeconds)}`;
    const playButton = (
        <button type="button" className="play-btn" onClick={handleTogglePlay} disabled={!player.isReady}>
            {player.isPlaying ? "⏸" : "▶"}
        </button>
    );

    return (
        <WavePanel
            compact={compact}
            playButton={playButton}
            view={
                <WaveformView
                    containerRef={player.containerRef}
                    isPlaying={player.isPlaying}
                    traces={NO_TRACES}
                    playheadFraction={null}
                    notice={compact && player.hasFailed ? AUDIO_UNAVAILABLE_NOTICE : null}
                />
            }
            readout={readout}
            failure={player.hasFailed ? AUDIO_UNAVAILABLE_NOTICE.text : null}
            controls={
                rateOptions.length > 1 && (
                    <label>
                        Rate
                        <select value={rateHz} onChange={handleRateChange}>
                            {rateOptions.map((option) => (
                                <option key={option.rateHz} value={option.rateHz}>
                                    {describeRateOption(option)}
                                </option>
                            ))}
                        </select>
                    </label>
                )
            }
            download={<DownloadLink href={sampleAudioUrl(sampleHash)} fileName={fileName} label="Save this sample" />}
        />
    );
}
