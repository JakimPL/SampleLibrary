// Kept equal to `NOMINAL_WAV_RATE` in `samplecore/storage/audio_store.py`, the header rate of every stored WAV.
export const NOMINAL_WAV_RATE_HZ = 44100;

const AS_THE_FILE_STATES = 1;

/** The wavesurfer playback rate that reproduces a sample's real, tracker-intended pitch. */
export function playbackRateFor(playbackRateHz: number): number {
    return playbackRateHz / NOMINAL_WAV_RATE_HZ;
}

/**
 * How fast to run a stored file so it sounds at the rate its caller named.
 *
 * A caller with no rate to hand passes `null` and hears the file as stored, which is the honest
 * reading of a sample whose rate the catalog does not know, and the reading a render that states
 * its own rate asks for. Every player in the app reads this one rule.
 */
export function soundedRate(playbackRateHz: number | null): number {
    return playbackRateHz === null ? AS_THE_FILE_STATES : playbackRateFor(playbackRateHz);
}

/**
 * How long a stored file really sounds: the length its frames take at the nominal rate, stretched
 * or shortened by the speed the library runs it at.
 *
 * A sample the catalog reads slower than the file states lasts longer than the file does, which is
 * the length it takes beside anything else heard with it.
 */
export function heardSeconds(storedSeconds: number, playbackRateHz: number | null): number {
    return storedSeconds / soundedRate(playbackRateHz);
}
