import { heardSeconds } from "../samples/nominalRate";
import { useSampleDetail } from "../samples/useSampleDetail";

/** One end of a morph as the panel reads it: what it is called, the rate it is heard at, and how long it lasts at that rate. */
export interface EndpointReading {
    readonly name: string;
    readonly rateHz: number | null;
    readonly heardSeconds: number | null;
}

const UNREAD: EndpointReading = { name: "", rateHz: null, heardSeconds: null };

/**
 * One end of a morph, read from the detail the catalog holds for it.
 *
 * `heardSeconds` is the length the sample really sounds: the stored file lasts as long as its
 * frames at the nominal rate, and running it at the rate the library plays it at stretches or
 * shortens it by that ratio. The inference process carries each end into the pair's own frame at
 * exactly that length, so this is the span an end takes against the render between them.
 */
export function useEndpoint(sampleHash: string): EndpointReading {
    const state = useSampleDetail(sampleHash);
    if (state.status !== "success") {
        return UNREAD;
    }
    const { sample } = state.data;
    return {
        name: sample.display_name,
        rateHz: sample.playback_rate_hz,
        heardSeconds: heardSeconds(sample.duration_seconds, sample.playback_rate_hz),
    };
}
