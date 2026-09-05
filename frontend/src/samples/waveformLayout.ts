import type { WaveformPeak } from "../api/samples";

const CENTER_DIVISOR = 2;

export interface WaveformBar {
    readonly x: number;
    readonly width: number;
    readonly yTop: number;
    readonly yBottom: number;
}

export function layoutWaveformBars(
    peaks: readonly WaveformPeak[],
    canvasWidth: number,
    canvasHeight: number,
): readonly WaveformBar[] {
    if (peaks.length === 0) {
        return [];
    }

    const halfHeight = canvasHeight / CENTER_DIVISOR;
    const barWidth = canvasWidth / peaks.length;
    return peaks.map((peak, index) => ({
        x: index * barWidth,
        width: barWidth,
        yTop: halfHeight - peak.maximum * halfHeight,
        yBottom: halfHeight - peak.minimum * halfHeight,
    }));
}
