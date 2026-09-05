import type { RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

import { playbackRateFor } from "./nominalRate";

const WAVEFORM_HEIGHT_PX = 96;
const MIN_PIXELS_PER_SECOND = 100;

export interface WaveformPlayer {
    readonly containerRef: RefObject<HTMLDivElement | null>;
    readonly isReady: boolean;
    readonly isPlaying: boolean;
    readonly currentTimeSeconds: number;
    readonly durationSeconds: number;
    readonly play: () => void;
    readonly pause: () => void;
    readonly seek: (seconds: number) => void;
    readonly setRateHz: (occurrenceRateHz: number) => void;
}

/**
 * Wraps one wavesurfer.js instance scoped to a single sample's audio -- the only file in this
 * codebase touching wavesurfer's own API. Decoding the real audio via Web Audio, rather than
 * rendering our own coarse preview peaks, gives the panel a properly detailed, scrollable contour.
 * `setRateHz` takes the occurrence's real tracker rate and never preserves pitch when applying
 * it: a tracker occurrence's rate is its pitch, not an independent tempo control.
 */
export function useWaveformPlayer(audioUrl: string, initialRateHz: number): WaveformPlayer {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const waveSurferRef = useRef<WaveSurfer | null>(null);
    const [isReady, setIsReady] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTimeSeconds, setCurrentTimeSeconds] = useState(0);
    const [durationSeconds, setDurationSeconds] = useState(0);

    useEffect(() => {
        const container = containerRef.current;
        if (container === null) {
            return undefined;
        }

        setIsReady(false);
        setIsPlaying(false);
        setCurrentTimeSeconds(0);
        setDurationSeconds(0);

        const waveSurfer = WaveSurfer.create({
            container,
            url: audioUrl,
            height: WAVEFORM_HEIGHT_PX,
            minPxPerSec: MIN_PIXELS_PER_SECOND,
            normalize: true,
            autoScroll: true,
            autoCenter: true,
        });
        waveSurfer.setPlaybackRate(playbackRateFor(initialRateHz), false);
        waveSurferRef.current = waveSurfer;

        waveSurfer.on("ready", (duration) => {
            setIsReady(true);
            setDurationSeconds(duration);
        });
        waveSurfer.on("play", () => {
            setIsPlaying(true);
        });
        waveSurfer.on("pause", () => {
            setIsPlaying(false);
        });
        waveSurfer.on("finish", () => {
            setIsPlaying(false);
        });
        waveSurfer.on("timeupdate", (currentTime) => {
            setCurrentTimeSeconds(currentTime);
        });

        return (): void => {
            waveSurfer.destroy();
            waveSurferRef.current = null;
        };
        // initialRateHz seeds only the moment this sample's instance is created; later rate changes
        // go through setRateHz, not a recreate, so it is deliberately left out of this dependency list.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [audioUrl]);

    return {
        containerRef,
        isReady,
        isPlaying,
        currentTimeSeconds,
        durationSeconds,
        play: () => {
            void waveSurferRef.current?.play();
        },
        pause: () => {
            waveSurferRef.current?.pause();
        },
        seek: (seconds: number) => {
            waveSurferRef.current?.setTime(seconds);
        },
        setRateHz: (occurrenceRateHz: number) => {
            waveSurferRef.current?.setPlaybackRate(playbackRateFor(occurrenceRateHz), false);
        },
    };
}
