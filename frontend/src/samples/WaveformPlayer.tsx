import type { ChangeEvent, ReactElement } from "react";

import { sampleAudioUrl } from "../api/samples";
import { formatDuration } from "../shared/format";
import { useWaveformPlayer } from "./useWaveformPlayer";

interface WaveformPlayerProps {
    readonly sampleHash: string;
    readonly rateHz: number;
    readonly rateOptions: readonly number[];
    readonly onRateChange: (rateHz: number) => void;
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
                <label>
                    Rate
                    <select value={rateHz} onChange={handleRateChange}>
                        {rateOptions.map((option) => (
                            <option key={option} value={option}>
                                {option} Hz
                            </option>
                        ))}
                    </select>
                </label>
                <span className="rate-info mono">{rateHz} Hz</span>
            </div>
        </div>
    );
}
