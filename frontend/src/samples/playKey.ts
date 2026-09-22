import type { KeyboardEvent } from "react";

import type { PreviewSource } from "./useAudioPreview";

const PLAY_KEY = " ";

/** Plays `source` when the key is the space bar, which a focused row's link answers to; reports whether it did. */
export function playOnSpace(
    event: KeyboardEvent<HTMLElement>,
    source: PreviewSource,
    play: (source: PreviewSource) => void,
): boolean {
    if (event.key !== PLAY_KEY) {
        return false;
    }
    event.preventDefault();
    play(source);
    return true;
}
