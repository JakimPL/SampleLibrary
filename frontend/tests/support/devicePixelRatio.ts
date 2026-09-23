import { onTestFinished } from "vitest";

/** Sets the screen's density for the rest of the test, restoring the environment's own when it finishes. */
export function stubDevicePixelRatio(ratio: number): void {
    const previous = window.devicePixelRatio;
    Object.defineProperty(window, "devicePixelRatio", { value: ratio, configurable: true, writable: true });
    onTestFinished(() => {
        Object.defineProperty(window, "devicePixelRatio", { value: previous, configurable: true, writable: true });
    });
}
