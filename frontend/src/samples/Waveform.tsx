import type { ReactElement } from "react";
import { useEffect, useRef } from "react";

import { sampleAudioUrl, type WaveformPeak } from "../api/samples";
import { layoutWaveformBars } from "./waveformLayout";

const CANVAS_WIDTH = 800;
const CANVAS_HEIGHT = 160;

interface WaveformProps {
    readonly sampleHash: string;
    readonly peaks: readonly WaveformPeak[];
}

export function Waveform({ sampleHash, peaks }: WaveformProps): ReactElement {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);

    useEffect(() => {
        const context = canvasRef.current?.getContext("2d");
        if (!context) {
            return;
        }

        context.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
        context.fillStyle = "currentColor";
        for (const bar of layoutWaveformBars(peaks, CANVAS_WIDTH, CANVAS_HEIGHT)) {
            context.fillRect(bar.x, bar.yTop, bar.width, bar.yBottom - bar.yTop);
        }
    }, [peaks]);

    return (
        <div>
            <canvas ref={canvasRef} width={CANVAS_WIDTH} height={CANVAS_HEIGHT} />
            {/* eslint-disable-next-line jsx-a11y/media-has-caption -- a raw audio sample preview has no speech to caption */}
            <audio controls src={sampleAudioUrl(sampleHash)} />
        </div>
    );
}
