import { useCallback, useSyncExternalStore } from "react";

import { sampleAudioUrl } from "../api/samples";
import { playbackRateFor } from "./nominalRate";

/** One thing the shared preview element can play: where its audio is, the key it is reported under, and the rate to run it at, or `null` to run it at the rate the file states. */
export interface PreviewSource {
    readonly key: string;
    readonly url: string;
    readonly playbackRateHz: number | null;
}

let audioElement: HTMLAudioElement | null = null;
let playingKey: string | null = null;
const listeners = new Set<() => void>();

function notify(): void {
    for (const listener of listeners) {
        listener();
    }
}

function stop(): void {
    audioElement?.pause();
    playingKey = null;
    notify();
}

/** How fast to run the stored file so a preview sounds at the rate its caller named.
 *
 * A caller with no rate to hand passes ``null`` and hears the file as stored, which is the honest
 * reading of a sample whose rate the catalog does not know.
 */
export function previewPlaybackRate(playbackRateHz: number | null): number {
    return playbackRateHz === null ? 1 : playbackRateFor(playbackRateHz);
}

/** A stored sample as a preview source, keyed by its own hash. */
export function samplePreview(sampleHash: string, playbackRateHz: number | null): PreviewSource {
    return { key: sampleHash, url: sampleAudioUrl(sampleHash), playbackRateHz };
}

function play(source: PreviewSource): void {
    audioElement ??= new Audio();
    audioElement.addEventListener("ended", stop, { once: true });
    audioElement.src = source.url;
    // Loading a source resets the rate to its default, so both carry the sample's rate after the source
    // is set; a tracker's rate is its pitch, so the pitch follows the rate.
    const playbackRate = previewPlaybackRate(source.playbackRateHz);
    audioElement.preservesPitch = false;
    audioElement.defaultPlaybackRate = playbackRate;
    audioElement.playbackRate = playbackRate;
    playingKey = source.key;
    notify();
    audioElement.play().catch(stop);
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => {
        listeners.delete(listener);
    };
}

function getSnapshot(): string | null {
    return playingKey;
}

export interface AudioPreview {
    readonly playingKey: string | null;
    readonly play: (source: PreviewSource) => void;
}

/** One shared audio element every preview plays through, so starting a new preview always stops
 * whichever one is currently playing rather than layering two sounds at once.
 *
 * A stored WAV carries a fixed header rate, so a caller that knows the rate the library really
 * plays a sample at passes it and hears it at that speed. Passing ``null`` sounds the file as
 * stored, which is what a caller with no rate to hand can honestly do. A morph plays through the
 * same element, keyed by its own URL, so the panel and the cloud agree on what is sounding.
 */
export function useAudioPreview(): AudioPreview {
    const currentlyPlayingKey = useSyncExternalStore(subscribe, getSnapshot);
    const playSource = useCallback((source: PreviewSource) => {
        play(source);
    }, []);

    return { playingKey: currentlyPlayingKey, play: playSource };
}
