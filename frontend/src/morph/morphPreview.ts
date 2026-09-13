import { morphAudioUrl } from "../api/morph";
import type { PreviewSource } from "../samples/useAudioPreview";

/**
 * A morph as something the shared preview player plays: its render's own URL, which is also the
 * key the player reports it under. The render states the rate the pair is heard at, so it plays
 * as the file says. The one place a morph turns into a source, so the panel and the cloud's marker
 * play the very same thing.
 */
export function morphPreview(first: string, second: string, weight: number): PreviewSource {
    const url = morphAudioUrl(first, second, weight);
    return { key: url, url, playbackRateHz: null };
}
