import type { ReactElement } from "react";
import { useEffect, useRef } from "react";

import type { WaveformPeak } from "../api/samples";
import { useThemeSignal } from "../theme/useThemeSignal";
import { readMiniWaveformColor } from "./miniWaveformColor";
import { PlayButton } from "./PlayButton";
import { layoutWaveformBars } from "./waveformLayout";

const THUMBNAIL_WIDTH = 64;
const THUMBNAIL_HEIGHT = 20;
const NO_THUMBNAIL_LABEL = "—";

interface ThumbnailProps {
    readonly sampleHash: string;
    readonly peaks: readonly WaveformPeak[] | null;
    readonly playbackRateHz: number | null;
}

export function Thumbnail({ sampleHash, peaks, playbackRateHz }: ThumbnailProps): ReactElement {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const themeSignal = useThemeSignal();

    useEffect(() => {
        const context = canvasRef.current?.getContext("2d");
        if (!context || !peaks) {
            return;
        }

        context.clearRect(0, 0, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT);
        context.fillStyle = readMiniWaveformColor();
        for (const bar of layoutWaveformBars(peaks, THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)) {
            context.fillRect(bar.x, bar.yTop, bar.width, bar.yBottom - bar.yTop);
        }
    }, [peaks, themeSignal.preference, themeSignal.systemVersion]);

    if (!peaks) {
        return <span aria-hidden="true">{NO_THUMBNAIL_LABEL}</span>;
    }

    return (
        <PlayButton sampleHash={sampleHash} playbackRateHz={playbackRateHz}>
            <canvas ref={canvasRef} width={THUMBNAIL_WIDTH} height={THUMBNAIL_HEIGHT} />
        </PlayButton>
    );
}
