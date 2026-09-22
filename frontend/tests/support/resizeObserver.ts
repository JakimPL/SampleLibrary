import { onTestFinished, vi } from "vitest";

const observersByElement = new Map<Element, Set<ControllableResizeObserver>>();

/** A stand-in for the browser's observer whose observations are delivered by `resizeTo`. */
export class ControllableResizeObserver implements ResizeObserver {
    private readonly callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
    }

    observe(target: Element): void {
        let observers = observersByElement.get(target);
        if (observers === undefined) {
            observers = new Set();
            observersByElement.set(target, observers);
        }
        observers.add(this);
    }

    unobserve(target: Element): void {
        observersByElement.get(target)?.delete(this);
    }

    disconnect(): void {
        for (const observers of observersByElement.values()) {
            observers.delete(this);
        }
    }

    deliver(target: Element, width: number, height: number): void {
        const contentRect = {
            x: 0,
            y: 0,
            width,
            height,
            top: 0,
            right: width,
            bottom: height,
            left: 0,
        } as DOMRectReadOnly;
        const entry = { target, contentRect } as ResizeObserverEntry;
        this.callback([entry], this);
    }
}

/**
 * Installs `ControllableResizeObserver` as the global for the rest of the test and restores the
 * setup file's silent stub when the test finishes.
 */
export function installControllableResizeObserver(): void {
    const previous = globalThis.ResizeObserver;
    vi.stubGlobal("ResizeObserver", ControllableResizeObserver);
    onTestFinished(() => {
        vi.stubGlobal("ResizeObserver", previous);
        observersByElement.clear();
    });
}

/** Reports `element` at the given size to every observer watching it. */
export function resizeTo(element: Element, width: number, height: number): void {
    for (const observer of observersByElement.get(element) ?? []) {
        observer.deliver(element, width, height);
    }
}
