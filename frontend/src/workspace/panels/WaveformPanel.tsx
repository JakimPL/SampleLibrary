import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import type { components } from "../../api/schema";
import { REFERENCE_NOTE } from "../../samples/nominalRate";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { type NoteOption, type RateOption, WaveformPlayer } from "../../samples/WaveformPlayer";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

type NotePlayed = components["schemas"]["SampleNotePlayed"];

interface FocusedWaveformProps {
    readonly sampleHash: string;
}

function rateOptionsByOccurrenceCount(rates: readonly number[]): RateOption[] {
    const occurrenceCountByRate = new Map<number, number>();
    for (const rate of rates) {
        occurrenceCountByRate.set(rate, (occurrenceCountByRate.get(rate) ?? 0) + 1);
    }

    return Array.from(occurrenceCountByRate, ([rateHz, occurrenceCount]) => ({ rateHz, occurrenceCount })).sort(
        (first, second) => first.rateHz - second.rateHz,
    );
}

function noteOptionsFrom(notesPlayed: readonly NotePlayed[]): NoteOption[] {
    return notesPlayed.map((note) => ({
        soundedNote: note.sounded_note,
        noteName: note.note_name,
        eventCount: note.event_count,
    }));
}

/** The note the library leans on most, which is the pitch a preview should open at. */
function mostPlayedNote(noteOptions: readonly NoteOption[]): number {
    let chosen = REFERENCE_NOTE;
    let highestCount = 0;
    for (const option of noteOptions) {
        if (option.eventCount > highestCount) {
            chosen = option.soundedNote;
            highestCount = option.eventCount;
        }
    }

    return chosen;
}

function FocusedWaveform({ sampleHash }: FocusedWaveformProps): ReactElement {
    const state = useSampleDetail(sampleHash);
    const [selectedRateHz, setSelectedRateHz] = useState<number | null>(null);
    const [selectedNote, setSelectedNote] = useState<number | null>(null);

    useEffect(() => {
        setSelectedRateHz(null);
        setSelectedNote(null);
    }, [sampleHash]);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const { sample } = state.data;
    const rateOptions = rateOptionsByOccurrenceCount(
        sample.occurrences.map((occurrence) => occurrence.properties.rate),
    );
    const [firstRateOption] = rateOptions;
    if (firstRateOption === undefined) {
        return <p className="no-selection">This sample has no occurrences to play at a real tracker rate.</p>;
    }

    const defaultRateHz = sample.dominant_rate_hz ?? firstRateOption.rateHz;
    const rateHz =
        selectedRateHz !== null && rateOptions.some((option) => option.rateHz === selectedRateHz)
            ? selectedRateHz
            : defaultRateHz;

    const noteOptions = noteOptionsFrom(sample.notes_played);
    const soundedNote =
        selectedNote !== null && noteOptions.some((option) => option.soundedNote === selectedNote)
            ? selectedNote
            : mostPlayedNote(noteOptions);

    return (
        <WaveformPlayer
            sampleHash={sample.hash}
            rateHz={rateHz}
            rateOptions={rateOptions}
            onRateChange={setSelectedRateHz}
            soundedNote={soundedNote}
            noteOptions={noteOptions}
            onNoteChange={setSelectedNote}
        />
    );
}

export function WaveformPanel(): ReactElement {
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);

    if (focusedSampleHash === null) {
        return <p className="no-selection">No sample focused yet — double-click a sample to hear it here.</p>;
    }

    return <FocusedWaveform sampleHash={focusedSampleHash} />;
}
