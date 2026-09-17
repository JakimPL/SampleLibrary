import type { ReactElement } from "react";
import { useMemo } from "react";

import { morphAudioUrl } from "../api/morph";
import type { SamplePreview, WaveformPeak } from "../api/samples";
import { useAudioPreview, usePreviewProgress } from "../samples/useAudioPreview";
import { useSamplePreview } from "../samples/useSamplePreview";
import { useWaveformPlayer } from "../samples/useWaveformPlayer";
import { NO_TRACES, type WaveformTrace, WaveformView } from "../samples/WaveformView";
import type { FetchState } from "../shared/fetchState";
import { formatDuration } from "../shared/format";
import { useThemeSignal } from "../theme/useThemeSignal";
import { readMorphColors } from "./morphColors";
import { morphPreview } from "./morphPreview";
import type { EndpointReading } from "./useEndpoint";

const AT_THE_FIRST_END = 0;
const WHOLE_FRAME = 1;
const NOTHING_DRAWN_HINT = "Let the slider go to hear a point on the path and see it drawn.";

interface MorphWaveformProps {
    readonly first: string;
    readonly second: string;
    readonly firstReading: EndpointReading;
    readonly secondReading: EndpointReading;
    /** The weight of the render on screen, or `null` while no point of the path has been asked for yet. */
    readonly renderedWeight: number | null;
    readonly available: boolean;
}

function peaksOf(state: FetchState<SamplePreview>): readonly WaveformPeak[] | null {
    return state.status === "success" ? state.data.thumbnail : null;
}

function traceOf(
    peaks: readonly WaveformPeak[] | null,
    seconds: number | null,
    axisSeconds: number,
    color: string,
): WaveformTrace | null {
    if (peaks === null || peaks.length === 0 || seconds === null) {
        return null;
    }
    return { peaks, share: seconds / axisSeconds, color };
}

/**
 * The morph as a waveform, over the traces of the two samples it runs between.
 *
 * The frame spans the longer end, which holds still as the weight moves: a render lasts the
 * geometric path between the two ends' own lengths, so it always falls between them, and each end
 * keeps the length it is heard at in the pair's frame. Every contour therefore stands where it
 * really falls in time, an end's trace drawn from the thumbnail the catalog already holds and the
 * render decoded as the detailed contour over them.
 *
 * The render sounds through the one preview element every sample plays through, which is what the
 * cloud's own marker plays as well, so a weight let go in either place is heard once. The waveform
 * follows that sound rather than making it -- the playhead is drawn from where the element stands,
 * and wavesurfer keeps its own cursor to itself -- and the play button sounds the point already
 * drawn again.
 */
export function MorphWaveform({
    first,
    second,
    firstReading,
    secondReading,
    renderedWeight,
    available,
}: MorphWaveformProps): ReactElement {
    const firstPreview = useSamplePreview(first);
    const secondPreview = useSamplePreview(second);
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
    const player = useWaveformPlayer(renderUrl, {
        rateHz: null,
        axisSeconds,
        interactive: false,
        waveColor: colors.between,
    });

    const traces = useMemo((): readonly WaveformTrace[] => {
        if (axisSeconds === null) {
            return NO_TRACES;
        }
        return [
            traceOf(peaksOf(firstPreview), firstReading.heardSeconds, axisSeconds, colors.first),
            traceOf(peaksOf(secondPreview), secondReading.heardSeconds, axisSeconds, colors.second),
        ].filter((trace): trace is WaveformTrace => trace !== null);
    }, [firstPreview, secondPreview, firstReading.heardSeconds, secondReading.heardSeconds, axisSeconds, colors]);

    const sounding = renderUrl !== null && progress.key === renderUrl;
    const playheadFraction =
        sounding && axisSeconds !== null ? Math.min(WHOLE_FRAME, progress.currentTimeSeconds / axisSeconds) : null;

    function replay(): void {
        if (renderedWeight !== null) {
            play(morphPreview(first, second, renderedWeight));
        }
    }

    return (
        <div className="wave-panel morph-wave">
            <WaveformView
                containerRef={player.containerRef}
                isPlaying={player.isPlaying}
                traces={traces}
                playheadFraction={playheadFraction}
            />
            <div className="transport">
                <button
                    type="button"
                    className="play-btn"
                    aria-label="Play the morph"
                    onClick={replay}
                    disabled={renderedWeight === null || !available}
                >
                    ▶
                </button>
                {renderUrl === null ? (
                    <span className="cell-muted">{NOTHING_DRAWN_HINT}</span>
                ) : (
                    <span className="time">
                        {formatDuration(sounding ? progress.currentTimeSeconds : 0)} /{" "}
                        {formatDuration(player.durationSeconds)}
                    </span>
                )}
            </div>
            {failure?.key === renderUrl && (
                <p className="panel-status error-notice" role="alert">
                    {`The morph could not be played: ${failure.message}.`}
                </p>
            )}
        </div>
    );
}
