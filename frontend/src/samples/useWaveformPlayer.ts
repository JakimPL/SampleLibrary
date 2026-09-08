import type { RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

import { readThemeColor } from "../theme/readThemeColor";
import { useThemeSignal } from "../theme/useThemeSignal";
import { playbackRateFor } from "./nominalRate";

const MIN_PIXELS_PER_SECOND = 100;
const CURSOR_WIDTH_PX = 2;

// Caps how tall the waveform is allowed to grow relative to its container's width -- a safety net
// for a narrow, portrait-oriented panel, not a target shape: a typical wide panel is meant to use
// most of its available height, only a container narrower than this ratio actually gets capped
// short of its full height, centered in the remaining space rather than stretched taller still.
const MIN_WAVEFORM_WIDTH_TO_HEIGHT_RATIO = 2;
const MIN_WAVEFORM_HEIGHT_PX = 32;

const WAVE_COLOR_PROPERTY = "--wave-fill";
const WAVE_COLOR_FALLBACK = "#b9bec9";
const PROGRESS_COLOR_PROPERTY = "--wave-progress";
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

function waveformHeightFor(containerWidthPx: number, containerHeightPx: number): number {
    const maxHeightForAspectRatio = containerWidthPx / MIN_WAVEFORM_WIDTH_TO_HEIGHT_RATIO;
    return Math.max(MIN_WAVEFORM_HEIGHT_PX, Math.min(containerHeightPx, maxHeightForAspectRatio));
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
 * The rendered height is likewise recomputed and re-applied on every container resize: wavesurfer's
 * own resize handling only reacts to a change in *width* unless `height` is literally the string
 * `"auto"`, which would fill the container's full height with no aspect-ratio cap.
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

        const initialSize = container.getBoundingClientRect();
        const waveSurfer = WaveSurfer.create({
            container,
            url: audioUrl,
            height: waveformHeightFor(initialSize.width, initialSize.height),
            cursorWidth: CURSOR_WIDTH_PX,
            minPxPerSec: MIN_PIXELS_PER_SECOND,
            normalize: true,
            autoScroll: true,
            autoCenter: true,
            ...readWaveformColors(),
        });
        waveSurfer.setPlaybackRate(playbackRateFor(initialRateHz), false);
        waveSurferRef.current = waveSurfer;

        let lastAppliedHeightPx = waveformHeightFor(initialSize.width, initialSize.height);
        const resizeObserver = new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry === undefined) {
                return;
            }

            const nextHeightPx = waveformHeightFor(entry.contentRect.width, entry.contentRect.height);
            if (nextHeightPx !== lastAppliedHeightPx) {
                lastAppliedHeightPx = nextHeightPx;
                waveSurfer.setOptions({ height: nextHeightPx });
            }
        });
        resizeObserver.observe(container);

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
            resizeObserver.disconnect();
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
