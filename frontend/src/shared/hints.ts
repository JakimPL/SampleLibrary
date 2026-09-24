import type { InputMode } from "../layout/layoutMode";

export type HintId = "noSample" | "noModule" | "noWaveform" | "morphSlotIdle" | "morphSlotSelected";

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

    morphSlotIdle: {
        pointer: "click, then a sample",
        touch: "tap, then a sample",
    },
    morphSlotSelected: {
        pointer: "now click a sample",
        touch: "now tap a sample",
    },
};

export function hintFor(id: HintId, input: InputMode): string {
    return HINTS[id][input];
}
