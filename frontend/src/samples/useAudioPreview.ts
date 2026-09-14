import { useCallback, useSyncExternalStore } from "react";

import { sampleAudioUrl } from "../api/samples";
import { playbackRateFor } from "./nominalRate";

/** One thing the shared preview element can play: where its audio is, the key it is reported under, and the rate to run it at, or `null` to run it at the rate the file states. */
export interface PreviewSource {
    readonly key: string;
    readonly url: string;
    readonly playbackRateHz: number | null;
}

/** A preview that could not be played: which one, and what the browser said about it. */
export interface PreviewFailure {
    readonly key: string;
    readonly message: string;
}

interface PreviewState {
    readonly playingKey: string | null;
    readonly failure: PreviewFailure | null;
}

const UNPLAYABLE_MESSAGE = "the audio could not be played";

let audioElement: HTMLAudioElement | null = null;
let state: PreviewState = { playingKey: null, failure: null };
let playSequence = 0;
const listeners = new Set<() => void>();

function publish(next: PreviewState): void {
    state = next;
    for (const listener of listeners) {
        listener();
    }
}

function sharedElement(): HTMLAudioElement {
    if (audioElement === null) {
        audioElement = new Audio();
        audioElement.addEventListener("ended", () => {
            publish({ ...state, playingKey: null });
        });
    }
    return audioElement;
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

function isSuperseded(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError";
}

function play(source: PreviewSource): void {
    playSequence += 1;
    const sequence = playSequence;
    const element = sharedElement();
    element.src = source.url;
    // Loading a source resets the rate to its default, so both carry the sample's rate after the source
    // is set; a tracker's rate is its pitch, so the pitch follows the rate.
    const playbackRate = previewPlaybackRate(source.playbackRateHz);
    element.preservesPitch = false;
    element.defaultPlaybackRate = playbackRate;
    element.playbackRate = playbackRate;
    publish({ playingKey: source.key, failure: null });
    element.play().catch((error: unknown) => {
        // A play the next one replaced rejects as it is cut off, which says nothing about the sound now playing.
        if (sequence !== playSequence || isSuperseded(error)) {
            return;
        }
        element.pause();
        publish({
            playingKey: null,
            failure: { key: source.key, message: error instanceof Error ? error.message : UNPLAYABLE_MESSAGE },
        });
    });
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => {
        listeners.delete(listener);
    };
}

function getSnapshot(): PreviewState {
    return state;
}

export interface AudioPreview {
    readonly playingKey: string | null;
    readonly failure: PreviewFailure | null;
    readonly play: (source: PreviewSource) => void;
}

/** One shared audio element every preview plays through, so starting a new preview always stops
 * whichever one is currently playing rather than layering two sounds at once.
 *
 * A stored WAV carries a fixed header rate, so a caller that knows the rate the library really
 * plays a sample at passes it and hears it at that speed. Passing ``null`` sounds the file as
 * stored, which is what a caller with no rate to hand can honestly do. A morph plays through the
 * same element, keyed by its own URL, so the panel and the cloud agree on what is sounding. A
 * preview the browser cannot play is reported under its key until the next one starts.
 */
export function useAudioPreview(): AudioPreview {
    const current = useSyncExternalStore(subscribe, getSnapshot);
    const playSource = useCallback((source: PreviewSource) => {
        play(source);
    }, []);

    return { playingKey: current.playingKey, failure: current.failure, play: playSource };
}
