import type { ChangeEvent, ReactElement } from "react";

import { sampleAudioUrl } from "../api/samples";
import { formatDuration } from "../shared/format";
import { useWaveformPlayer } from "./useWaveformPlayer";

export interface RateOption {
    readonly rateHz: number;
    readonly eventCount: number;
}

interface WaveformPlayerProps {
    readonly sampleHash: string;
    readonly rateHz: number;
    readonly rateOptions: readonly RateOption[];
    readonly onRateChange: (rateHz: number) => void;
}

function describeRateOption(option: RateOption): string {
    const timeWord = option.eventCount === 1 ? "time" : "times";
    return `${String(option.rateHz)} Hz · played ${String(option.eventCount)} ${timeWord}`;
}

export function WaveformPlayer({ sampleHash, rateHz, rateOptions, onRateChange }: WaveformPlayerProps): ReactElement {
    const player = useWaveformPlayer(sampleAudioUrl(sampleHash), rateHz);

    function handleTogglePlay(): void {
        if (player.isPlaying) {
            player.pause();
        } else {
            player.play();
        }
    }

    function handleRateChange(event: ChangeEvent<HTMLSelectElement>): void {
        const nextRateHz = Number(event.target.value);
        onRateChange(nextRateHz);
        player.setRateHz(nextRateHz);
    }

    return (
        <div className="wave-panel">
            <div className="wave-canvas-wrap" ref={player.containerRef} />
            <div className="transport">
                <button type="button" className="play-btn" onClick={handleTogglePlay} disabled={!player.isReady}>
                    {player.isPlaying ? "⏸" : "▶"}
                </button>
                <span className="time">
                    {formatDuration(player.currentTimeSeconds)} / {formatDuration(player.durationSeconds)}
                </span>
                {rateOptions.length > 1 && (
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
                )}
            </div>
        </div>
    );
}
