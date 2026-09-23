import type { ReactElement } from "react";

import type { WaveformPeak } from "../api/samples";
import { MiniWaveform } from "./MiniWaveform";
import { PlayButton } from "./PlayButton";

const NO_THUMBNAIL_LABEL = "—";

interface ThumbnailProps {
    readonly sampleHash: string;
    readonly peaks: readonly WaveformPeak[] | null;
    readonly playbackRateHz: number | null;
}

/** A row's thumbnail: the sample's stored contour on its play button, or a dash where none is stored. */
export function Thumbnail({ sampleHash, peaks, playbackRateHz }: ThumbnailProps): ReactElement {
    if (!peaks) {
        return <span aria-hidden="true">{NO_THUMBNAIL_LABEL}</span>;
    }

    return (
        <PlayButton sampleHash={sampleHash} playbackRateHz={playbackRateHz}>
            <MiniWaveform peaks={peaks} />
        </PlayButton>
    );
}
