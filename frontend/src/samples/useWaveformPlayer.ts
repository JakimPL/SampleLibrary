import type { RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

import { readThemeColor } from "../theme/readThemeColor";
import { useThemeSignal } from "../theme/useThemeSignal";
import { playbackRateFor } from "./nominalRate";

const WAVEFORM_HEIGHT_PX = 96;
const MIN_PIXELS_PER_SECOND = 100;

const WAVE_COLOR_PROPERTY = "--wave-fill";
const WAVE_COLOR_FALLBACK = "#b9bec9";
const PROGRESS_COLOR_PROPERTY = "--accent";
const PROGRESS_COLOR_FALLBACK = "#a8690f";
const CURSOR_COLOR_PROPERTY = "--wave-cursor";
const CURSOR_COLOR_FALLBACK = "#a8690f";

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

interface WaveformColors {
    readonly waveColor: string;
    readonly progressColor: string;
    readonly cursorColor: string;
}

function readWaveformColors(): WaveformColors {
    return {
        waveColor: readThemeColor(WAVE_COLOR_PROPERTY, WAVE_COLOR_FALLBACK),
        progressColor: readThemeColor(PROGRESS_COLOR_PROPERTY, PROGRESS_COLOR_FALLBACK),
        cursorColor: readThemeColor(CURSOR_COLOR_PROPERTY, CURSOR_COLOR_FALLBACK),
    };
}

/**
 * Wraps one wavesurfer.js instance scoped to a single sample's audio -- the only file in this
 * codebase touching wavesurfer's own API. Decoding the real audio via Web Audio, rather than
 * rendering our own coarse preview peaks, gives the panel a properly detailed, scrollable contour.
 * `setRateHz` takes the occurrence's real tracker rate and never preserves pitch when applying
 * it: a tracker occurrence's rate is its pitch, not an independent tempo control. Waveform colors
 * are read from the theme's CSS custom properties at creation, and re-applied through wavesurfer's
 * own `setOptions` whenever `useThemeSignal` reports the resolved theme could have changed, since
 * a canvas-backed visual cannot pick up a `var()` change on its own the way a styled element does.
 */
export function useWaveformPlayer(audioUrl: string, initialRateHz: number): WaveformPlayer {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const waveSurferRef = useRef<WaveSurfer | null>(null);
    const [isReady, setIsReady] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTimeSeconds, setCurrentTimeSeconds] = useState(0);
    const [durationSeconds, setDurationSeconds] = useState(0);
    const themeSignal = useThemeSignal();

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
            ...readWaveformColors(),
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

    useEffect(() => {
        // Redundantly re-applies the colors the mount effect above just set on the first render.
        waveSurferRef.current?.setOptions(readWaveformColors());
    }, [themeSignal.preference, themeSignal.systemVersion]);

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
