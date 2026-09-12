import { morphAudioUrl } from "../api/morph";
import type { PreviewSource } from "../samples/useAudioPreview";
import { morphPlaybackRateHz } from "./morphRate";

/**
 * A morph as something the shared preview player plays: its render's own URL, which is also the
 * key the player reports it under, and the rate the two ends' rates put it at. The one place a
 * morph turns into a source, so the panel and the cloud's marker play the very same thing.
 */
export function morphPreview(
    first: string,
    second: string,
    weight: number,
    firstRateHz: number | null,
    secondRateHz: number | null,
): PreviewSource {
    const url = morphAudioUrl(first, second, weight);
    return { key: url, url, playbackRateHz: morphPlaybackRateHz(firstRateHz, secondRateHz, weight) };
}
