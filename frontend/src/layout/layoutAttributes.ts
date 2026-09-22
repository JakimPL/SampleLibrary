import { useEffect } from "react";

import type { LayoutSignal } from "./layoutMode";
import { useLayoutMode } from "./useLayoutMode";

/** Writes the signal onto the root element, so a stylesheet keys off `data-layout` and `data-input`. */
export function applyLayoutSignal(root: HTMLElement, signal: LayoutSignal): void {
    root.dataset.layout = signal.layout;
    root.dataset.input = signal.input;
}

/** Keeps the document's root attributes equal to the live layout signal for as long as the app renders. */
export function useLayoutAttributes(): void {
    const signal = useLayoutMode();
    useEffect(() => {
        applyLayoutSignal(document.documentElement, signal);
    }, [signal]);
}
