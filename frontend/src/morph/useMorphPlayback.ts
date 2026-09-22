import { useAudioPreview } from "../samples/useAudioPreview";
import { morphPreview } from "./morphPreview";
import { useMorphStore } from "./morphStore";
import { type MorphStatus, useMorphStatus } from "./useMorphStatus";

export interface MorphPlayback {
    readonly status: MorphStatus;
    /**
     * Sounds the pair at its current weight, while both ends are chosen and a renderer answers,
     * and records that point as the one drawn on screen.
     */
    readonly hearCurrentPoint: () => void;
}

/**
 * The one way a point of the morph is heard: the strip's slider and play button and the marker on
 * the cloud all come through here, so a weight let go anywhere plays once through the shared
 * preview element and is drawn wherever the render is shown.
 */
export function useMorphPlayback(): MorphPlayback {
    const status = useMorphStatus();
    const { play } = useAudioPreview();
    const markRendered = useMorphStore((state) => state.markRendered);

    function hearCurrentPoint(): void {
        const { first, second, weight } = useMorphStore.getState();
        if (first === null || second === null || !status.available) {
            return;
        }
        markRendered();
        play(morphPreview(first, second, weight));
    }

    return { status, hearCurrentPoint };
}
