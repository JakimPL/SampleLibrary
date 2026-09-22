import type { RefObject } from "react";
import { useEffect, useState } from "react";

/**
 * The width, in whole CSS pixels, of the element `ref` holds: read once on mount and again on every
 * resize, and `null` until the element exists. A panel reads this where its columns are decided in
 * code; everything a stylesheet can decide on its own reads a container query instead.
 */
export function useContainerWidth(ref: RefObject<HTMLElement | null>): number | null {
    const [width, setWidth] = useState<number | null>(null);

    useEffect(() => {
        const element = ref.current;
        if (element === null) {
            return undefined;
        }

        function apply(measured: number): void {
            const rounded = Math.round(measured);
            setWidth((current) => (current === rounded ? current : rounded));
        }

        apply(element.getBoundingClientRect().width);
        const observer = new ResizeObserver((entries) => {
            const entry = entries[0];
            if (entry !== undefined) {
                apply(entry.contentRect.width);
            }
        });
        observer.observe(element);
        return (): void => {
            observer.disconnect();
        };
    }, [ref]);

    return width;
}
