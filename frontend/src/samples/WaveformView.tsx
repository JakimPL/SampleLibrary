import type { ReactElement, RefObject } from "react";
import { useEffect, useRef, useState } from "react";

import type { WaveformPeak } from "../api/samples";
import { classNames } from "../shared/classNames";
import { useThemeSignal } from "../theme/useThemeSignal";
import { layoutWaveformBars } from "./waveformLayout";

const PERCENT_OF_A_SHARE = 100;

/** One contour drawn behind the waveform: the peaks to draw, the share of the width they span, and the color they wear. */
export interface WaveformTrace {
    readonly peaks: readonly WaveformPeak[];
    readonly share: number;
    readonly color: string;
}

export const NO_TRACES: readonly WaveformTrace[] = [];

interface CanvasSize {
    readonly width: number;
    readonly height: number;
}

const UNMEASURED: CanvasSize = { width: 0, height: 0 };

interface WaveformViewProps {
    readonly containerRef: RefObject<HTMLDivElement | null>;
    readonly isPlaying: boolean;
    readonly traces: readonly WaveformTrace[];
    readonly playheadFraction: number | null;
}

/**
 * The frame a waveform is drawn in: whatever contours stand behind it, the host wavesurfer draws
 * into, and a playhead for a sound coming from elsewhere.
 *
 * A trace is drawn from the stored thumbnail peaks over its own share of the width, so contours of
 * different lengths sharing one axis read against each other where they really fall. Each is
 * repainted whenever the resolved theme could have changed, the way every canvas-backed visual in
 * the app is, and whenever the frame is resized, since a canvas holds the pixels it was given.
 */
export function WaveformView({ containerRef, isPlaying, traces, playheadFraction }: WaveformViewProps): ReactElement {
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
            setSize((current) => (current.width === width && current.height === height ? current : { width, height }));
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

        context.clearRect(0, 0, size.width, size.height);
        for (const trace of traces) {
            context.fillStyle = trace.color;
            for (const bar of layoutWaveformBars(trace.peaks, size.width * trace.share, size.height)) {
                context.fillRect(bar.x, bar.yTop, bar.width, bar.yBottom - bar.yTop);
            }
        }
    }, [traces, size, themeSignal.preference, themeSignal.systemVersion]);

    return (
        <div className={classNames("wave-canvas-wrap", isPlaying && "is-playing")} ref={wrapRef}>
            {traces.length > 0 && (
                <canvas
                    className="wave-traces"
                    ref={traceCanvasRef}
                    width={size.width}
                    height={size.height}
                    aria-hidden
                />
            )}
            <div className="wave-host" ref={containerRef} />
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
