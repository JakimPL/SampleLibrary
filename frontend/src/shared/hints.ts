import type { InputMode } from "../layout/layoutMode";

export type HintId = "noSample" | "noModule" | "noWaveform" | "noPair" | "cloudIdle";

/** What an empty panel says, worded for the gestures the person's input actually has. */
const HINTS: Readonly<Record<HintId, Readonly<Record<InputMode, string>>>> = {
    noSample: {
        pointer: "No sample open. Double-click a sample in a list or the cloud, or select one and press Enter.",
        touch: "No sample open. Tap › on a sample to open it.",
    },
    noModule: {
        pointer: "No module open. Double-click a module in the Modules list, or select one and press Enter.",
        touch: "No module open. Tap › on a module to open it.",
    },
    noWaveform: {
        pointer: "Open a sample to play it here: double-click it, or press Enter on its row.",
        touch: "Open a sample to play it here.",
    },
    cloudIdle: {
        pointer: "Click a point to hear it. Drag to move, scroll to zoom. Right-click a point to pair it.",
        touch: "Tap a point to hear it. Drag to move, pinch to zoom. Hold a point for more.",
    },
    noPair: {
        pointer:
            "Pick two samples to morph between: right-drag between two cloud points, or click A and Shift-click B in a list. The pair stays here while you browse.",
        touch: "Pick two samples to morph between: choose Morph from here on one and Morph to here on another.",
    },
};

export function hintFor(id: HintId, input: InputMode): string {
    return HINTS[id][input];
}
