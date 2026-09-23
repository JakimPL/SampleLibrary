import type { RefObject } from "react";
import { useEffect, useState } from "react";

/** The box a canvas fills: its CSS size, and the device pixels per CSS pixel it is backed at. */
export interface CanvasBox {
    readonly width: number;
    readonly height: number;
    /** Device pixels per CSS pixel, which the canvas is backed at so its drawing stays as sharp as the screen allows. */
    readonly ratio: number;
}

/** The bitmap behind a box: its CSS size in whole device pixels. */
export interface CanvasBitmap {
    readonly width: number;
    readonly height: number;
}

export const UNMEASURED_CANVAS_BOX: CanvasBox = { width: 0, height: 0, ratio: 1 };
const WHOLE_RATIO = 1;

export function bitmapOf(box: CanvasBox): CanvasBitmap {
    return { width: Math.round(box.width * box.ratio), height: Math.round(box.height * box.ratio) };
}

/**
 * The size of the element `ref` holds, read once on mount and again on every resize, with the
 * screen's density beside it: what a canvas filling that element is backed at, so its drawing
 * follows the box the stylesheet gives it and stays sharp on a dense screen. The sizes stay in
 * CSS pixels; `bitmapOf` gives the canvas its attributes, and the same ratio goes on the context's
 * transform so the drawing code works in CSS pixels. An equal reading keeps the same box, so a
 * drawing effect keyed on it runs only for a real change.
 */
export function useCanvasBox(ref: RefObject<HTMLElement | null>): CanvasBox {
    const [box, setBox] = useState<CanvasBox>(UNMEASURED_CANVAS_BOX);

    useEffect(() => {
        const element = ref.current;
        if (element === null) {
            return undefined;
        }

        function apply(width: number, height: number): void {
            const ratio = window.devicePixelRatio || WHOLE_RATIO;
            setBox((current) =>
                current.width === width && current.height === height && current.ratio === ratio
                    ? current
                    : { width, height, ratio },
            );
        }

        const bounds = element.getBoundingClientRect();
        apply(bounds.width, bounds.height);
        const observer = new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry !== undefined) {
                apply(entry.contentRect.width, entry.contentRect.height);
            }
        });
        observer.observe(element);
        return (): void => {
            observer.disconnect();
        };
    }, [ref]);

    return box;
}
