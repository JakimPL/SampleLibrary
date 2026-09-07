// Every stored WAV carries this fixed header rate regardless of the tracker's real intended rate
// (`NOMINAL_WAV_RATE` in `samplecore/storage/audio_store.py`), so a decoder plays it back at this
// rate unless told otherwise.
export const NOMINAL_WAV_RATE_HZ = 44100;

// Tracker tuning counts from C-5: an occurrence's stored rate is the speed its waveform plays at
// when that key is pressed (`RATE_NOTE` in `trackmod/spec/pitch.py`).
export const REFERENCE_NOTE = 60;
const NOTES_PER_OCTAVE = 12;
const OCTAVE_RATIO = 2;

/** The rate a sample's frames are read at to sound one note against an occurrence's own rate. */
export function soundingRateHz(referenceRateHz: number, soundedNote: number): number {
    return referenceRateHz * Math.pow(OCTAVE_RATIO, (soundedNote - REFERENCE_NOTE) / NOTES_PER_OCTAVE);
}

/** The wavesurfer playback rate that reproduces a sample's real, tracker-intended pitch. */
export function playbackRateFor(occurrenceRateHz: number): number {
    return occurrenceRateHz / NOMINAL_WAV_RATE_HZ;
}
