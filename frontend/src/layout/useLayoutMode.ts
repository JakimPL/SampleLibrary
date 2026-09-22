import { useSyncExternalStore } from "react";

import {
    COARSE_POINTER_MEDIA_QUERY,
    inputModeOf,
    layoutModeOf,
    type LayoutSignal,
    PHONE_MEDIA_QUERY,
} from "./layoutMode";

const SIGNAL_QUERIES = [PHONE_MEDIA_QUERY, COARSE_POINTER_MEDIA_QUERY] as const;

let lastSignal: LayoutSignal | null = null;

function matches(query: string): boolean {
    return window.matchMedia(query).matches;
}

/** Reads the signal afresh, handing back the previous object while nothing changed so React sees one snapshot. */
function readLayoutSignal(): LayoutSignal {
    const next: LayoutSignal = {
        layout: layoutModeOf(matches(PHONE_MEDIA_QUERY)),
        input: inputModeOf(matches(COARSE_POINTER_MEDIA_QUERY)),
    };
    if (lastSignal !== null && lastSignal.layout === next.layout && lastSignal.input === next.input) {
        return lastSignal;
    }
    lastSignal = next;
    return next;
}

function subscribeToSignalQueries(onChange: () => void): () => void {
    const lists = SIGNAL_QUERIES.map((query) => window.matchMedia(query));
    for (const list of lists) {
        list.addEventListener("change", onChange);
    }
    return (): void => {
        for (const list of lists) {
            list.removeEventListener("change", onChange);
        }
    };
}

/**
 * The shell and the input mode the viewport asks for, kept live: a window resized across the
 * workspace threshold, a tablet gaining a mouse, or a phone turned on its side all publish a change.
 */
export function useLayoutMode(): LayoutSignal {
    return useSyncExternalStore(subscribeToSignalQueries, readLayoutSignal, readLayoutSignal);
}
