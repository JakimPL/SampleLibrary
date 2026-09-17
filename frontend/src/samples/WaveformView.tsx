import type { ReactElement, RefObject } from "react";
import { useEffect, useRef, useState } from "react";

import type { WaveformPeak } from "../api/samples";
import { classNames } from "../shared/classNames";
import { useThemeSignal } from "../theme/useThemeSignal";
import { layoutWaveformBars, type WaveformBar } from "./waveformLayout";

const PERCENT_OF_A_SHARE = 100;

/** How a contour is drawn: solid for the one being read, as its own outline for one standing beside it. */
export type ContourStyle = "filled" | "outlined";

/** One contour in the frame: the peaks to draw, the share of the width they span, the color they wear, and how they are drawn. */
export interface WaveformTrace {
    readonly peaks: readonly WaveformPeak[];
    readonly share: number;
    readonly color: string;
    readonly style: ContourStyle;
}

export const NO_TRACES: readonly WaveformTrace[] = [];

/** A word standing where a contour would: what it says, and whether it says something went wrong. */
export interface WaveformNotice {
    readonly text: string;
    readonly failed: boolean;
}

interface CanvasSize {
    readonly width: number;
    readonly height: number;
    /** Device pixels per CSS pixel, which the canvas is backed at so its contours stay as sharp as the screen allows. */
    readonly ratio: number;
}

const UNMEASURED: CanvasSize = { width: 0, height: 0, ratio: 1 };
const WHOLE_RATIO = 1;

/**
 * One contour as a single shape, running along its maxima and back along its minima.
 *
 * A shape holds its color however many buckets fall within a pixel, where a rectangle per bucket
 * thins to a sliver the canvas draws as a fraction of that color, leaving a dense contour pale.
 * Its edge is always drawn, one device pixel wide, so a quiet passage whose extremes lie a
 * fraction of a pixel apart still reads as a line. An outlined contour is that edge alone, which
 * is what lets a taller envelope stand beside a shorter one rather than swallowing it.
 */
function drawContour(
    context: CanvasRenderingContext2D,
    bars: readonly WaveformBar[],
    trace: WaveformTrace,
    hairline: number,
): void {
    if (bars.length === 0) {
        return;
    }
    context.beginPath();
    for (const bar of bars) {
        context.lineTo(bar.x, bar.yTop);
    }
    for (let index = bars.length - 1; index >= 0; index -= 1) {
        const bar = bars[index];
        if (bar !== undefined) {
            context.lineTo(bar.x, bar.yBottom);
        }
    }
    context.closePath();
    if (trace.style === "filled") {
        context.fillStyle = trace.color;
        context.fill();
    }
    context.strokeStyle = trace.color;
    context.lineWidth = hairline;
    context.stroke();
}

interface WaveformViewProps {
    /** The host a waveform library draws into, or `null` for a frame whose contours are all drawn here. */
    readonly containerRef: RefObject<HTMLDivElement | null> | null;
    readonly isPlaying: boolean;
    readonly traces: readonly WaveformTrace[];
    readonly playheadFraction: number | null;
    readonly notice: WaveformNotice | null;
}

/**
 * The frame a waveform is drawn in: whatever contours stand behind it, the host wavesurfer draws
 * into, and a playhead for a sound coming from elsewhere.
 *
 * A trace is drawn over its own share of the width, so contours of different lengths sharing one
 * axis read against each other where they really fall. Each is repainted whenever the resolved
 * theme could have changed, the way every canvas-backed visual in the app is, and whenever the
 * frame is resized, since a canvas holds the pixels it was given. A notice stands in the frame
 * itself where a contour is missing, so the reason is read where the contour would have been
 * rather than in a row of its own.
 */
export function WaveformView({
    containerRef,
    isPlaying,
    traces,
    playheadFraction,
    notice,
}: WaveformViewProps): ReactElement {
    const wrapRef = useRef<HTMLDivElement | null>(null);
    const traceCanvasRef = useRef<HTMLCanvasElement | null>(null);
    const [size, setSize] = useState<CanvasSize>(UNMEASURED);
    const themeSignal = useThemeSignal();

    useEffect(() => {
        const wrap = wrapRef.current;
        if (wrap === null) {
            return undefined;
        }

        function apply(width: number, height: number): void {
            const ratio = window.devicePixelRatio || WHOLE_RATIO;
            setSize((current) =>
                current.width === width && current.height === height && current.ratio === ratio
                    ? current
                    : { width, height, ratio },
            );
        }

        const bounds = wrap.getBoundingClientRect();
        apply(bounds.width, bounds.height);
        const observer = new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry !== undefined) {
                apply(entry.contentRect.width, entry.contentRect.height);
            }
        });
        observer.observe(wrap);
        return (): void => {
            observer.disconnect();
        };
    }, []);

    useEffect(() => {
        const context = traceCanvasRef.current?.getContext("2d");
        if (!context) {
            return;
        }

        context.setTransform(size.ratio, 0, 0, size.ratio, 0, 0);
        context.clearRect(0, 0, size.width, size.height);
        const hairline = WHOLE_RATIO / size.ratio;
        for (const trace of traces) {
            drawContour(
                context,
                layoutWaveformBars(trace.peaks, size.width * trace.share, size.height),
                trace,
                hairline,
            );
        }
    }, [traces, size, themeSignal.preference, themeSignal.systemVersion]);

    return (
        <div className={classNames("wave-canvas-wrap", isPlaying && "is-playing")} ref={wrapRef}>
            {traces.length > 0 && (
                <canvas
                    className="wave-traces"
                    ref={traceCanvasRef}
                    width={size.width * size.ratio}
                    height={size.height * size.ratio}
                    aria-hidden
                />
            )}
            {containerRef !== null && <div className="wave-host" ref={containerRef} />}
            {notice !== null && (
                <p
                    className={classNames("wave-notice", notice.failed && "wave-notice-failed")}
                    {...(notice.failed ? { role: "status" } : {})}
                >
                    {notice.text}
                </p>
            )}
            {playheadFraction !== null && (
                <div
                    className="wave-playhead"
                    style={{ left: `${String(playheadFraction * PERCENT_OF_A_SHARE)}%` }}
                    aria-hidden
                />
            )}
        </div>
    );
}
