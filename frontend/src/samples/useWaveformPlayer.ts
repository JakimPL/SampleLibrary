import type { RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

import { readThemeColor } from "../theme/readThemeColor";
import { useThemeSignal } from "../theme/useThemeSignal";
import { soundedRate } from "./nominalRate";

const MIN_PIXELS_PER_SECOND = 100;
const CURSOR_WIDTH_PX = 2;

const MIN_WAVEFORM_WIDTH_TO_HEIGHT_RATIO = 2;
const MIN_WAVEFORM_HEIGHT_PX = 32;

const WAVE_COLOR_PROPERTY = "--wave-fill";
const WAVE_COLOR_FALLBACK = "#b9bec9";
const PROGRESS_COLOR_PROPERTY = "--wave-progress";
const PROGRESS_COLOR_FALLBACK = "#a8690f";
const CURSOR_COLOR_PROPERTY = "--wave-cursor";
const CURSOR_COLOR_FALLBACK = "#a8690f";

/** How a waveform is drawn and sounded: the rate it plays at, the seconds its width stands for, whether a pointer seeks it, and the color it wears. */
export interface WaveformOptions {
    readonly rateHz: number | null;
    readonly axisSeconds: number | null;
    readonly interactive: boolean;
    readonly waveColor: string | null;
}

export interface WaveformPlayer {
    readonly containerRef: RefObject<HTMLDivElement | null>;
    readonly isReady: boolean;
    readonly hasFailed: boolean;
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

function readWaveformColors(waveColor: string | null): WaveformColors {
    return {
        waveColor: waveColor ?? readThemeColor(WAVE_COLOR_PROPERTY, WAVE_COLOR_FALLBACK),
        progressColor: readThemeColor(PROGRESS_COLOR_PROPERTY, PROGRESS_COLOR_FALLBACK),
        cursorColor: readThemeColor(CURSOR_COLOR_PROPERTY, CURSOR_COLOR_FALLBACK),
    };
}

function waveformHeightFor(containerWidthPx: number, containerHeightPx: number): number {
    const maxHeightForAspectRatio = containerWidthPx / MIN_WAVEFORM_WIDTH_TO_HEIGHT_RATIO;
    return Math.max(MIN_WAVEFORM_HEIGHT_PX, Math.min(containerHeightPx, maxHeightForAspectRatio));
}

interface AxisDrawing {
    readonly minPxPerSec: number;
    readonly fillParent: boolean;
    readonly autoScroll: boolean;
    readonly autoCenter: boolean;
    readonly hideScrollbar: boolean;
}

/**
 * How wide a second is drawn.
 *
 * With no axis named, a second takes a fixed number of pixels and the contour scrolls under a
 * cursor it keeps centered, which is what reads a long sample closely. An axis of so many seconds
 * fits exactly that span to the container instead, so audio shorter than the axis takes its own
 * share of the width and whatever is drawn beside it stands second for second against it.
 */
function axisDrawing(axisSeconds: number | null, containerWidthPx: number): AxisDrawing {
    if (axisSeconds === null) {
        return {
            minPxPerSec: MIN_PIXELS_PER_SECOND,
            fillParent: true,
            autoScroll: true,
            autoCenter: true,
            hideScrollbar: false,
        };
    }
    return {
        minPxPerSec: containerWidthPx / axisSeconds,
        fillParent: false,
        autoScroll: false,
        autoCenter: false,
        hideScrollbar: true,
    };
}

/**
 * Wraps one wavesurfer.js instance scoped to a single audio source -- the only file in this
 * codebase touching wavesurfer's own API, and holding an instance for as long as there is a source
 * to draw. Decoding the real audio via Web Audio, rather than
 * rendering our own coarse preview peaks, gives the panel a properly detailed contour.
 * `setRateHz` takes the occurrence's real tracker rate and never preserves pitch when applying
 * it: a tracker occurrence's rate is its pitch, not an independent tempo control, and a source
 * stating its own rate is sounded as it stands. Waveform colors are read from the theme's CSS
 * custom properties at creation, with a caller's own color standing in for the theme's fill where
 * one is given, and re-applied through wavesurfer's own `setOptions` whenever `useThemeSignal`
 * reports the resolved theme could have changed, since a canvas-backed visual cannot pick up a
 * `var()` change on its own the way a styled element does. The rendered height and, for a fixed
 * axis, the pixels each second takes are likewise recomputed and re-applied on every container
 * resize: wavesurfer's own resize handling only reacts to a change in *width* unless `height` is
 * literally the string `"auto"`, which would fill the container's full height with no
 * aspect-ratio cap.
 */
export function useWaveformPlayer(audioUrl: string | null, options: WaveformOptions): WaveformPlayer {
    const { rateHz, axisSeconds, interactive, waveColor } = options;
    const containerRef = useRef<HTMLDivElement | null>(null);
    const waveSurferRef = useRef<WaveSurfer | null>(null);
    const playbackRateRef = useRef(soundedRate(rateHz));
    const [isReady, setIsReady] = useState(false);
    const [hasFailed, setHasFailed] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTimeSeconds, setCurrentTimeSeconds] = useState(0);
    const [durationSeconds, setDurationSeconds] = useState(0);
    const themeSignal = useThemeSignal();

    useEffect(() => {
        const container = containerRef.current;
        if (container === null || audioUrl === null) {
            return undefined;
        }

        setIsReady(false);
        setHasFailed(false);
        setIsPlaying(false);
        setCurrentTimeSeconds(0);
        setDurationSeconds(0);

        playbackRateRef.current = soundedRate(rateHz);
        const initialSize = container.getBoundingClientRect();
        const waveSurfer = WaveSurfer.create({
            container,
            url: audioUrl,
            height: waveformHeightFor(initialSize.width, initialSize.height),
            cursorWidth: CURSOR_WIDTH_PX,
            normalize: true,
            interact: interactive,
            ...axisDrawing(axisSeconds, initialSize.width),
            ...readWaveformColors(waveColor),
        });
        waveSurferRef.current = waveSurfer;

        let lastAppliedHeightPx = waveformHeightFor(initialSize.width, initialSize.height);
        let lastAppliedPixelsPerSecond = axisDrawing(axisSeconds, initialSize.width).minPxPerSec;
        const resizeObserver = new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry === undefined) {
                return;
            }

            const nextHeightPx = waveformHeightFor(entry.contentRect.width, entry.contentRect.height);
            const nextPixelsPerSecond = axisDrawing(axisSeconds, entry.contentRect.width).minPxPerSec;
            if (nextHeightPx !== lastAppliedHeightPx || nextPixelsPerSecond !== lastAppliedPixelsPerSecond) {
                lastAppliedHeightPx = nextHeightPx;
                lastAppliedPixelsPerSecond = nextPixelsPerSecond;
                waveSurfer.setOptions({ height: nextHeightPx, minPxPerSec: nextPixelsPerSecond });
            }
        });
        resizeObserver.observe(container);

        waveSurfer.on("ready", (duration) => {
            // Loading a source resets a media element's rate, so the rate applies once the file is ready.
            waveSurfer.setPlaybackRate(playbackRateRef.current, false);
            setIsReady(true);
            setDurationSeconds(duration);
        });
        waveSurfer.on("error", () => {
            setHasFailed(true);
        });
        waveSurfer.on("play", () => {
            setIsPlaying(true);
        });
        waveSurfer.on("pause", () => {
            setIsPlaying(false);
        });
        waveSurfer.on("finish", () => {
            // Rewinds, so a sample already heard looks the same as an untouched one.
            waveSurfer.setTime(0);
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
        // rateHz and waveColor seed a new instance alone; setRateHz and the theme effect carry every later one.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [audioUrl, axisSeconds, interactive]);

    useEffect(() => {
        waveSurferRef.current?.setOptions(readWaveformColors(waveColor));
    }, [waveColor, themeSignal.preference, themeSignal.systemVersion]);

    return {
        containerRef,
        isReady,
        hasFailed,
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
            playbackRateRef.current = soundedRate(occurrenceRateHz);
            waveSurferRef.current?.setPlaybackRate(playbackRateRef.current, false);
        },
    };
}
