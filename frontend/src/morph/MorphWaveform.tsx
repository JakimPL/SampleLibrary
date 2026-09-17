import type { ReactElement } from "react";
import { useMemo } from "react";

import { morphAudioUrl } from "../api/morph";
import { sampleAudioUrl } from "../api/samples";
import { type AudioReading, useAudioPeaks } from "../samples/audioPeaks";
import { useAudioPreview, usePreviewProgress } from "../samples/useAudioPreview";
import {
    type ContourStyle,
    NO_TRACES,
    type WaveformNotice,
    type WaveformTrace,
    WaveformView,
} from "../samples/WaveformView";
import { DownloadLink } from "../shared/DownloadLink";
import { formatDuration, shortHash } from "../shared/format";
import { useThemeSignal } from "../theme/useThemeSignal";
import { readMorphColors } from "./morphColors";
import { morphPreview } from "./morphPreview";
import type { EndpointReading } from "./useEndpoint";

// Enough buckets that a contour has one per pixel at any width a panel is given.
const TRACE_BUCKET_COUNT = 2048;
const AT_THE_FIRST_END = 0;
const WHOLE_FRAME = 1;
const NOTHING_DRAWN_HINT = "Let the slider go to hear a point on the path and see it drawn.";
const WAV_EXTENSION = ".wav";
const OFFLINE_HINT = "The path is drawn once an inference process answers for it.";

interface MorphWaveformProps {
    readonly first: string;
    readonly second: string;
    readonly firstReading: EndpointReading;
    readonly secondReading: EndpointReading;
    /** The weight of the render on screen, or `null` while no point of the path has been asked for yet. */
    readonly renderedWeight: number | null;
    readonly available: boolean;
}

function traceOf(
    reading: AudioReading,
    seconds: number | null,
    axisSeconds: number,
    color: string,
    style: ContourStyle,
): WaveformTrace | null {
    if (reading.peaks === null || seconds === null) {
        return null;
    }
    return { peaks: reading.peaks, share: Math.min(WHOLE_FRAME, seconds / axisSeconds), color, style };
}

/**
 * The morph as a waveform, over the traces of the two samples it runs between.
 *
 * The frame spans the longer end, which holds still as the weight moves: a render lasts the
 * geometric path between the two ends' own lengths, so it always falls between them, and each end
 * keeps the length it is heard at in the pair's frame. Every contour therefore stands where it
 * really falls in time, all three decoded in the browser at the same detail, so a render reads
 * against its ends as one drawing rather than against a coarser sketch of them.
 *
 * The render sounds through the one preview element every sample plays through, which is what the
 * cloud's own marker plays as well, so a weight let go in either place is heard once. The waveform
 * follows that sound rather than making it, and the play button sounds the point already drawn
 * again. Where a point is refused or cannot be read, the frame says so in the server's own words,
 * in the place the contour would have stood.
 */
export function MorphWaveform({
    first,
    second,
    firstReading,
    secondReading,
    renderedWeight,
    available,
}: MorphWaveformProps): ReactElement {
    const { play, failure } = useAudioPreview();
    const progress = usePreviewProgress();
    const themeSignal = useThemeSignal();

    const longestSeconds = Math.max(firstReading.heardSeconds ?? 0, secondReading.heardSeconds ?? 0);
    const axisSeconds = longestSeconds > 0 ? longestSeconds : null;
    const renderUrl = renderedWeight === null ? null : morphAudioUrl(first, second, renderedWeight);
    const colors = useMemo(
        () => readMorphColors(renderedWeight ?? AT_THE_FIRST_END),
        // eslint-disable-next-line react-hooks/exhaustive-deps -- the theme signal is what changes the colors read
        [renderedWeight, themeSignal.preference, themeSignal.systemVersion],
    );

    const firstAudio = useAudioPeaks(sampleAudioUrl(first), TRACE_BUCKET_COUNT);
    const secondAudio = useAudioPeaks(sampleAudioUrl(second), TRACE_BUCKET_COUNT);
    const render = useAudioPeaks(renderUrl, TRACE_BUCKET_COUNT);

    const traces = useMemo((): readonly WaveformTrace[] => {
        if (axisSeconds === null) {
            return NO_TRACES;
        }
        return [
            traceOf(firstAudio, firstReading.heardSeconds, axisSeconds, colors.first, "outlined"),
            traceOf(secondAudio, secondReading.heardSeconds, axisSeconds, colors.second, "outlined"),
            traceOf(render, render.seconds, axisSeconds, colors.between, "filled"),
        ].filter((trace): trace is WaveformTrace => trace !== null);
    }, [firstAudio, secondAudio, render, firstReading.heardSeconds, secondReading.heardSeconds, axisSeconds, colors]);

    const sounding = renderUrl !== null && progress.key === renderUrl;
    const playheadFraction =
        sounding && axisSeconds !== null ? Math.min(WHOLE_FRAME, progress.currentTimeSeconds / axisSeconds) : null;
    const playFailure = failure?.key === renderUrl ? failure.message : null;
    const notice = noticeOf(render.refusal ?? playFailure, renderedWeight, available);
    const canPlay = renderedWeight !== null && available && render.refusal === null;

    function replay(): void {
        if (renderedWeight !== null) {
            play(morphPreview(first, second, renderedWeight));
        }
    }

    return (
        <div className="wave-panel morph-wave">
            <WaveformView
                containerRef={null}
                isPlaying={sounding}
                traces={traces}
                playheadFraction={playheadFraction}
                notice={notice}
            />
            <div className="transport">
                <button
                    type="button"
                    className="play-btn"
                    aria-label="Play the morph"
                    onClick={replay}
                    disabled={!canPlay}
                >
                    ▶
                </button>
                <span className="time">
                    {formatDuration(sounding ? progress.currentTimeSeconds : 0)} / {formatDuration(render.seconds ?? 0)}
                </span>
                {renderUrl !== null && renderedWeight !== null && render.refusal === null && (
                    <DownloadLink
                        href={renderUrl}
                        fileName={renderFileName(first, second, renderedWeight)}
                        label="Save this render"
                    />
                )}
            </div>
        </div>
    );
}

/** What a saved render is named: the pair it runs between and the point along it. */
function renderFileName(first: string, second: string, weight: number): string {
    return `morph-${shortHash(first)}-${shortHash(second)}-${String(weight)}${WAV_EXTENSION}`;
}

/** What stands where the render would: why it was refused, or what is waited on before there is one. */
function noticeOf(failed: string | null, renderedWeight: number | null, available: boolean): WaveformNotice | null {
    if (failed !== null) {
        return { text: failed, failed: true };
    }
    if (renderedWeight !== null) {
        return null;
    }
    return { text: available ? NOTHING_DRAWN_HINT : OFFLINE_HINT, failed: false };
}
