// Every stored WAV carries this fixed header rate regardless of the tracker's real intended rate
// (`NOMINAL_WAV_RATE` in `samplecore/storage/audio_store.py`), so a decoder plays it back at this
// rate unless told otherwise.
export const NOMINAL_WAV_RATE_HZ = 44100;

/** The wavesurfer playback rate that reproduces a sample's real, tracker-intended pitch. */
export function playbackRateFor(playbackRateHz: number): number {
    return playbackRateHz / NOMINAL_WAV_RATE_HZ;
}
