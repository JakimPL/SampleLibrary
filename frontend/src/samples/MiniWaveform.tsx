import type { ReactElement } from "react";
import { useEffect, useRef } from "react";

import type { WaveformPeak } from "../api/samples";
import { useThemeSignal } from "../theme/useThemeSignal";
import { readMiniWaveformColor } from "./miniWaveformColor";
import { layoutWaveformBars } from "./waveformLayout";

const WAVEFORM_WIDTH_PX = 96;
const WAVEFORM_HEIGHT_PX = 28;

interface MiniWaveformProps {
    readonly peaks: readonly WaveformPeak[];
}

/** A glance-sized drawing of a sample's stored thumbnail, repainted whenever the theme changes. */
export function MiniWaveform({ peaks }: MiniWaveformProps): ReactElement {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const themeSignal = useThemeSignal();

    useEffect(() => {
        const context = canvasRef.current?.getContext("2d");
        if (!context) {
            return;
        }

        context.clearRect(0, 0, WAVEFORM_WIDTH_PX, WAVEFORM_HEIGHT_PX);
        context.fillStyle = readMiniWaveformColor();
        for (const bar of layoutWaveformBars(peaks, WAVEFORM_WIDTH_PX, WAVEFORM_HEIGHT_PX)) {
            context.fillRect(bar.x, bar.yTop, bar.width, bar.yBottom - bar.yTop);
        }
    }, [peaks, themeSignal.preference, themeSignal.systemVersion]);

    return <canvas ref={canvasRef} width={WAVEFORM_WIDTH_PX} height={WAVEFORM_HEIGHT_PX} />;
}
