import { useEffect } from "react";

import { useMorphStore } from "./morphStore";

export type UndoCommand = "undo" | "redo";

const UNDO_KEY = "z";
const REDO_KEY = "y";
/** The input types a person types text into, whose own undo the browser keeps. */
const TEXT_INPUT_TYPES: ReadonlySet<string> = new Set(["text", "search", "url", "email", "password", "number", "tel"]);

/** Whether a key pressed on `target` edits text there, where the browser's own undo applies: a text field, or an editable region. */
export function editsText(target: EventTarget | null): boolean {
    if (target instanceof HTMLTextAreaElement) {
        return true;
    }
    if (target instanceof HTMLInputElement) {
        return TEXT_INPUT_TYPES.has(target.type);
    }
    return target instanceof HTMLElement && target.closest("[contenteditable]") !== null;
}

/**
 * The command a key chord names: Ctrl+Z or ⌘Z undoes, and Ctrl+Y, Ctrl+Shift+Z or ⇧⌘Z redoes.
 * Alt rules a chord out, since AltGr on Windows reports itself as Ctrl with Alt; ⌘Y stays the
 * browser's own, which opens its history; and the key is read by its letter, so a QWERTZ layout
 * and a shifted Z both answer.
 */
export function undoCommandOf(event: KeyboardEvent): UndoCommand | null {
    if (event.altKey || event.isComposing) {
        return null;
    }
    const key = event.key.toLowerCase();
    if (key === UNDO_KEY && (event.ctrlKey || event.metaKey)) {
        return event.shiftKey ? "redo" : "undo";
    }
    if (key === REDO_KEY && event.ctrlKey && !event.metaKey && !event.shiftKey) {
        return "redo";
    }
    return null;
}

/**
 * Ctrl+Z and Ctrl+Y over the morph's ends from anywhere in the app, the text fields excepted,
 * where the browser's own undo keeps working.
 */
export function useMorphUndoKeys(): void {
    useEffect(() => {
        function handleKeyDown(event: KeyboardEvent): void {
            if (editsText(event.target)) {
                return;
            }
            const command = undoCommandOf(event);
            if (command === null) {
                return;
            }
            event.preventDefault();
            if (command === "undo") {
                useMorphStore.getState().undo();
            } else {
                useMorphStore.getState().redo();
            }
        }
        window.addEventListener("keydown", handleKeyDown);
        return (): void => {
            window.removeEventListener("keydown", handleKeyDown);
        };
    }, []);
}
