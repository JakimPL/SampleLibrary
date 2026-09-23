import { describe, expect, it } from "vitest";

import type { InputMode } from "../../src/layout/layoutMode";
import { tapPlays } from "../../src/workspace/rowTap";

interface TapCase {
    readonly name: string;
    readonly input: InputMode;
    readonly defaultPrevented: boolean;
    readonly target: "row" | "button";
    readonly plays: boolean;
}

const CASES: readonly TapCase[] = [
    {
        name: "a finger's tap the row took as a highlight",
        input: "touch",
        defaultPrevented: true,
        target: "row",
        plays: true,
    },
    { name: "a pointer's click", input: "pointer", defaultPrevented: true, target: "row", plays: false },
    { name: "a tap the row left alone", input: "touch", defaultPrevented: false, target: "row", plays: false },
    {
        name: "a tap on one of the row's own buttons",
        input: "touch",
        defaultPrevented: true,
        target: "button",
        plays: false,
    },
];

/** Where the click landed: a cell of the row, or a glyph inside one of the row's buttons. */
function targetOf(kind: TapCase["target"]): Element {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    row.append(cell);
    if (kind === "row") {
        return cell;
    }
    const button = document.createElement("button");
    const glyph = document.createElement("span");
    button.append(glyph);
    cell.append(button);
    return glyph;
}

describe("tapPlays", () => {
    it.each(CASES)("$name plays the row's sample: $plays", ({ input, defaultPrevented, target, plays }) => {
        expect(tapPlays(input, { defaultPrevented, target: targetOf(target) })).toBe(plays);
    });
});
