import { useCallback, useSyncExternalStore } from "react";

import { sampleAudioUrl } from "../api/samples";
import { playbackRateFor } from "./nominalRate";

let audioElement: HTMLAudioElement | null = null;
let playingHash: string | null = null;
const listeners = new Set<() => void>();

function notify(): void {
    for (const listener of listeners) {
        listener();
    }
}

function stop(): void {
    audioElement?.pause();
    playingHash = null;
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

function play(sampleHash: string, playbackRateHz: number | null): void {
    audioElement ??= new Audio();
    audioElement.addEventListener("ended", stop, { once: true });
    // A browser keeps a rate change from moving the pitch unless told otherwise, which is the
    // opposite of what a tracker does: the rate a sample is read at is its pitch, not a tempo
    // control.
    audioElement.preservesPitch = false;
    audioElement.playbackRate = previewPlaybackRate(playbackRateHz);
    audioElement.src = sampleAudioUrl(sampleHash);
    playingHash = sampleHash;
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
    return playingHash;
}

export interface AudioPreview {
    readonly playingHash: string | null;
    readonly play: (sampleHash: string, playbackRateHz: number | null) => void;
}

/** One shared audio element every Thumbnail plays through, so starting a new preview always stops
 * whichever one is currently playing rather than layering two sounds at once.
 *
 * A stored WAV carries a fixed header rate, so a caller that knows the rate the library really
 * plays a sample at passes it and hears it at that speed. Passing ``null`` sounds the file as
 * stored, which is what a caller with no rate to hand can honestly do.
 */
export function useAudioPreview(): AudioPreview {
    const currentlyPlayingHash = useSyncExternalStore(subscribe, getSnapshot);
    const playSample = useCallback((sampleHash: string, playbackRateHz: number | null) => {
        play(sampleHash, playbackRateHz);
    }, []);

    return { playingHash: currentlyPlayingHash, play: playSample };
}
