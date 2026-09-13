// Kept equal to `NOMINAL_WAV_RATE` in `samplecore/storage/audio_store.py`, the header rate of every stored WAV.
export const NOMINAL_WAV_RATE_HZ = 44100;

/** The wavesurfer playback rate that reproduces a sample's real, tracker-intended pitch. */
export function playbackRateFor(playbackRateHz: number): number {
    return playbackRateHz / NOMINAL_WAV_RATE_HZ;
}
