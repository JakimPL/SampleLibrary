import type { ReactElement } from "react";
import { useEffect, useRef } from "react";

import type { WaveformPeak } from "../api/samples";
import { bitmapOf, useCanvasBox } from "../layout/useCanvasBox";
import { useThemeSignal } from "../theme/useThemeSignal";
import { readMiniWaveformColor } from "./miniWaveformColor";
import { layoutWaveformBars } from "./waveformLayout";

interface MiniWaveformProps {
    readonly peaks: readonly WaveformPeak[];
}

/**
 * A sample's stored thumbnail drawn as bars over the box the stylesheet gives it, backed at the
 * screen's density and repainted whenever the box or the theme changes, so it reads sharp at any
 * size it is shown. The bars go down as one path, so their edges meet with no seam however they
 * fall across the pixels.
 */
export function MiniWaveform({ peaks }: MiniWaveformProps): ReactElement {
    const boxRef = useRef<HTMLDivElement | null>(null);
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const box = useCanvasBox(boxRef);
    const bitmap = bitmapOf(box);
    const themeSignal = useThemeSignal();

    useEffect(() => {
        const context = canvasRef.current?.getContext("2d");
        if (!context) {
            return;
        }

        context.setTransform(box.ratio, 0, 0, box.ratio, 0, 0);
        context.clearRect(0, 0, box.width, box.height);
        context.fillStyle = readMiniWaveformColor();
        context.beginPath();
        for (const bar of layoutWaveformBars(peaks, box.width, box.height)) {
            context.rect(bar.x, bar.yTop, bar.width, bar.yBottom - bar.yTop);
        }
        context.fill();
    }, [peaks, box, themeSignal.preference, themeSignal.systemVersion]);

    return (
        <div className="mini-waveform" ref={boxRef}>
            <canvas ref={canvasRef} width={bitmap.width} height={bitmap.height} aria-hidden />
        </div>
    );
}
