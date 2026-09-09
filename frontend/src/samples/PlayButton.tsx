import type { ReactElement, ReactNode } from "react";

import { useAudioPreview } from "./useAudioPreview";

interface PlayButtonProps {
    readonly sampleHash: string;
    readonly playbackRateHz: number | null;
    readonly children: ReactNode;
}

/** A bare, chrome-free button that plays one sample by hash, outlined while it's the one playing. */
export function PlayButton({ sampleHash, playbackRateHz, children }: PlayButtonProps): ReactElement {
    const { play, playingHash } = useAudioPreview();

    return (
        <button
            type="button"
            className="thumbnail-button"
            onClick={() => {
                play(sampleHash, playbackRateHz);
            }}
            aria-label="Play sample preview"
            aria-pressed={playingHash === sampleHash}
        >
            {children}
        </button>
    );
}
