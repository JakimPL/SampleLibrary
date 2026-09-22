import { describe, expect, it } from "vitest";

import { hintFor, type HintId } from "../../src/shared/hints";

const HINT_IDS: readonly HintId[] = [
    "noSample",
    "noModule",
    "noWaveform",
    "cloudIdle",
    "morphSlotIdle",
    "morphSlotSelected",
];

describe("hintFor", () => {
    it.each(HINT_IDS)("words %s for a pointer and for touch", (id) => {
        expect(hintFor(id, "pointer")).not.toBe("");
        expect(hintFor(id, "touch")).not.toBe("");
        expect(hintFor(id, "touch")).not.toMatch(/double-click|right-drag|Shift-click/i);
    });
});
