import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { useMorphStore } from "../../src/morph/morphStore";
import { editsText, type UndoCommand, undoCommandOf, useMorphUndoKeys } from "../../src/morph/useMorphUndoKeys";

const A = "a".repeat(64);
const B = "b".repeat(64);
const C = "c".repeat(64);

function chord(key: string, modifiers: Partial<KeyboardEventInit> = {}): KeyboardEvent {
    return new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...modifiers });
}

/** One key chord, and the command it names. */
interface ChordCase {
    readonly name: string;
    readonly key: string;
    readonly modifiers: Partial<KeyboardEventInit>;
    readonly command: UndoCommand | null;
}

const CHORD_CASES: readonly ChordCase[] = [
    { name: "Ctrl+Z undoes", key: "z", modifiers: { ctrlKey: true }, command: "undo" },
    { name: "⌘Z undoes", key: "z", modifiers: { metaKey: true }, command: "undo" },
    {
        name: "Ctrl+Shift+Z redoes, the key read as a capital",
        key: "Z",
        modifiers: { ctrlKey: true, shiftKey: true },
        command: "redo",
    },
    { name: "⇧⌘Z redoes", key: "z", modifiers: { metaKey: true, shiftKey: true }, command: "redo" },
    { name: "Ctrl+Y redoes", key: "y", modifiers: { ctrlKey: true }, command: "redo" },
    { name: "⌘Y stays the browser's", key: "y", modifiers: { metaKey: true }, command: null },
    {
        name: "Ctrl+Alt+Z, which AltGr reports, is left alone",
        key: "z",
        modifiers: { ctrlKey: true, altKey: true },
        command: null,
    },
    { name: "a plain Z is left alone", key: "z", modifiers: {}, command: null },
    { name: "Ctrl+Shift+Y is left alone", key: "y", modifiers: { ctrlKey: true, shiftKey: true }, command: null },
];

describe("undoCommandOf", () => {
    it.each(CHORD_CASES)("$name", ({ key, modifiers, command }: ChordCase) => {
        expect(undoCommandOf(chord(key, modifiers))).toBe(command);
    });
});

describe("editsText", () => {
    it("knows the fields a person types into", () => {
        const text = document.createElement("input");
        text.type = "text";
        const search = document.createElement("input");
        search.type = "search";
        const range = document.createElement("input");
        range.type = "range";
        const region = document.createElement("div");
        region.setAttribute("contenteditable", "true");

        expect(editsText(text)).toBe(true);
        expect(editsText(search)).toBe(true);
        expect(editsText(document.createElement("textarea"))).toBe(true);
        expect(editsText(region)).toBe(true);
        expect(editsText(range)).toBe(false);
        expect(editsText(document.createElement("button"))).toBe(false);
        expect(editsText(null)).toBe(false);
    });
});

function UndoKeys(): ReactElement {
    useMorphUndoKeys();
    return (
        <>
            <input type="text" aria-label="Filter" />
            <input type="range" aria-label="Point" />
        </>
    );
}

/** A pair with one change behind it: A and C, where A and B stood before. */
function changeOnce(): void {
    useMorphStore.getState().join(A, B);
    useMorphStore.getState().setEnd("second", C);
}

describe("useMorphUndoKeys", () => {
    it("undoes and redoes the ends from the keys, taking the chord for itself", () => {
        changeOnce();
        render(<UndoKeys />);

        const undoing = chord("z", { ctrlKey: true });
        fireEvent(window, undoing);
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B });
        expect(undoing.defaultPrevented).toBe(true);

        const redoing = chord("y", { ctrlKey: true });
        fireEvent(window, redoing);
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: C });
        expect(redoing.defaultPrevented).toBe(true);
    });

    it("leaves a text field's chord to the browser", () => {
        changeOnce();
        render(<UndoKeys />);

        const undoing = chord("z", { ctrlKey: true });
        fireEvent(screen.getByRole("textbox", { name: "Filter" }), undoing);

        expect(useMorphStore.getState()).toMatchObject({ first: A, second: C });
        expect(undoing.defaultPrevented).toBe(false);
    });

    it("still undoes from a slider", () => {
        changeOnce();
        render(<UndoKeys />);

        fireEvent(screen.getByRole("slider", { name: "Point" }), chord("z", { ctrlKey: true }));

        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B });
    });

    it("stops listening as it leaves", () => {
        changeOnce();
        const { unmount } = render(<UndoKeys />);
        unmount();

        fireEvent(window, chord("z", { ctrlKey: true }));

        expect(useMorphStore.getState()).toMatchObject({ first: A, second: C });
    });
});
