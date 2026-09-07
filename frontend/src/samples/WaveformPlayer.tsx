import type { ChangeEvent, ReactElement } from "react";

import { sampleAudioUrl } from "../api/samples";
import { formatDuration } from "../shared/format";
import { soundingRateHz } from "./nominalRate";
import { useWaveformPlayer } from "./useWaveformPlayer";

export interface RateOption {
    readonly rateHz: number;
    readonly occurrenceCount: number;
}

export interface NoteOption {
    readonly soundedNote: number;
    readonly noteName: string;
    readonly eventCount: number;
}

interface WaveformPlayerProps {
    readonly sampleHash: string;
    readonly rateHz: number;
    readonly rateOptions: readonly RateOption[];
    readonly onRateChange: (rateHz: number) => void;
    readonly soundedNote: number;
    readonly noteOptions: readonly NoteOption[];
    readonly onNoteChange: (soundedNote: number) => void;
}

function describeRateOption(option: RateOption): string {
    const occurrenceWord = option.occurrenceCount === 1 ? "occurrence" : "occurrences";
    return `${String(option.rateHz)} Hz · used in ${String(option.occurrenceCount)} ${occurrenceWord}`;
}

function describeNoteOption(option: NoteOption): string {
    const timeWord = option.eventCount === 1 ? "time" : "times";
    return `${option.noteName} · played ${String(option.eventCount)} ${timeWord}`;
}

export function WaveformPlayer({
    sampleHash,
    rateHz,
    rateOptions,
    onRateChange,
    soundedNote,
    noteOptions,
    onNoteChange,
}: WaveformPlayerProps): ReactElement {
    const player = useWaveformPlayer(sampleAudioUrl(sampleHash), soundingRateHz(rateHz, soundedNote));

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
        player.setRateHz(soundingRateHz(nextRateHz, soundedNote));
    }

    function handleNoteChange(event: ChangeEvent<HTMLSelectElement>): void {
        const nextNote = Number(event.target.value);
        onNoteChange(nextNote);
        player.setRateHz(soundingRateHz(rateHz, nextNote));
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
                            <option key={option.rateHz} value={option.rateHz}>
                                {describeRateOption(option)}
                            </option>
                        ))}
                    </select>
                </label>
                {noteOptions.length > 0 && (
                    <label>
                        Note
                        <select value={soundedNote} onChange={handleNoteChange}>
                            {noteOptions.map((option) => (
                                <option key={option.soundedNote} value={option.soundedNote}>
                                    {describeNoteOption(option)}
                                </option>
                            ))}
                        </select>
                    </label>
                )}
            </div>
            <p className="wave-caption">
                {noteOptions.length > 0
                    ? "Playback sounds the selected note against the selected rate, the way the library really plays this sample."
                    : "Playback pitch follows the selected rate, since a tracker sample carries no fixed rate of its own."}
            </p>
        </div>
    );
}
