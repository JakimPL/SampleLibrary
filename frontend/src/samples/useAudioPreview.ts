import { useCallback, useSyncExternalStore } from "react";

import { sampleAudioUrl } from "../api/samples";
import { playbackRateFor, REFERENCE_NOTE, soundingRateHz } from "./nominalRate";

/** The pitch to sound a preview at: an occurrence's own rate, and the note to play against it. */
export interface PreviewPitch {
    readonly rateHz: number;
    readonly soundedNote: number;
}

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

/** How fast to run the stored file so a preview sounds at the pitch its caller named.
 *
 * A caller with no rate to hand passes ``null`` and hears the file as stored, which is the honest
 * reading of a sample whose occurrences the catalog does not know.
 */
export function previewPlaybackRate(pitch: PreviewPitch | null): number {
    return pitch === null ? 1 : playbackRateFor(soundingRateHz(pitch.rateHz, pitch.soundedNote));
}

function play(sampleHash: string, pitch: PreviewPitch | null): void {
    audioElement ??= new Audio();
    audioElement.addEventListener("ended", stop, { once: true });
    // A browser keeps a rate change from moving the pitch unless told otherwise, which is the
    // opposite of what a tracker does: an occurrence's rate is its pitch, not a tempo control.
    audioElement.preservesPitch = false;
    audioElement.playbackRate = previewPlaybackRate(pitch);
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
    readonly play: (sampleHash: string, pitch: PreviewPitch | null) => void;
}

/** One shared audio element every Thumbnail plays through, so starting a new preview always stops
 * whichever one is currently playing rather than layering two sounds at once.
 *
 * A stored WAV carries a fixed header rate, so a caller that knows the rate and note the library
 * plays a sample at passes them and hears it at that pitch. Passing ``null`` sounds the file as
 * stored, which is what a caller with no rate to hand can honestly do.
 */
export function useAudioPreview(): AudioPreview {
    const currentlyPlayingHash = useSyncExternalStore(subscribe, getSnapshot);
    const playSample = useCallback((sampleHash: string, pitch: PreviewPitch | null) => {
        play(sampleHash, pitch);
    }, []);

    return { playingHash: currentlyPlayingHash, play: playSample };
}

/** The pitch for a listing row that knows a rate but not the note it is usually played at. */
export function pitchAtReferenceNote(rateHz: number | null | undefined): PreviewPitch | null {
    return rateHz === null || rateHz === undefined ? null : { rateHz, soundedNote: REFERENCE_NOTE };
}
