import type { ReactElement, ReactNode } from "react";

import type { PreviewPitch } from "./useAudioPreview";
import { useAudioPreview } from "./useAudioPreview";

interface PlayButtonProps {
    readonly sampleHash: string;
    readonly pitch: PreviewPitch | null;
    readonly children: ReactNode;
}

/** A bare, chrome-free button that plays one sample by hash, outlined while it's the one playing. */
export function PlayButton({ sampleHash, pitch, children }: PlayButtonProps): ReactElement {
    const { play, playingHash } = useAudioPreview();

    return (
        <button
            type="button"
            className="thumbnail-button"
            onClick={() => {
                play(sampleHash, pitch);
            }}
            aria-label="Play sample preview"
            aria-pressed={playingHash === sampleHash}
        >
            {children}
        </button>
    );
}
