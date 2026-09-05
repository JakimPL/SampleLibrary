import { useCallback, useSyncExternalStore } from "react";

import { sampleAudioUrl } from "../api/samples";

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

function play(sampleHash: string): void {
    audioElement ??= new Audio();
    audioElement.addEventListener("ended", stop, { once: true });
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
    readonly play: (sampleHash: string) => void;
}

/** One shared audio element every Thumbnail plays through, so starting a new preview always stops
 * whichever one is currently playing rather than layering two sounds at once.
 */
export function useAudioPreview(): AudioPreview {
    const currentlyPlayingHash = useSyncExternalStore(subscribe, getSnapshot);
    const playSample = useCallback((sampleHash: string) => {
        play(sampleHash);
    }, []);

    return { playingHash: currentlyPlayingHash, play: playSample };
}
