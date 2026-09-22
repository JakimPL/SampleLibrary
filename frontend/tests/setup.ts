import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { INITIAL_MORPH_STATE, useMorphStore } from "../src/morph/morphStore";
import { clearRequestCache } from "../src/shared/requestCache";
import { DEFAULT_THEME_PREFERENCE } from "../src/theme/themeOptions";
import { useThemeStore } from "../src/theme/themeStore";
import { INITIAL_SELECTION_STATE, useSelectionStore } from "../src/workspace/selectionStore";

afterEach(() => {
    cleanup();
});

// Module-level stores and caches outlive a test, so each one returns to its initial state here.
afterEach(() => {
    useSelectionStore.setState(INITIAL_SELECTION_STATE);
});

// Set directly, bypassing setPreference, so the reset leaves localStorage to the clear below.
afterEach(() => {
    useThemeStore.setState({ preference: DEFAULT_THEME_PREFERENCE });
    delete document.documentElement.dataset.theme;
});

// The layout attributes follow the live media queries, so a test that stubbed them leaves none behind.
afterEach(() => {
    delete document.documentElement.dataset.layout;
    delete document.documentElement.dataset.input;
});

afterEach(() => {
    clearRequestCache();
});

// Imported when the case ends, so a test file's mock of the API they call is the one they were loaded with.
afterEach(async () => {
    const { INITIAL_ANNOTATION_STATE, useAnnotationStore } = await import("../src/samples/annotationStore");
    const { resetAnnotationWriteQueue } = await import("../src/samples/annotationWriteQueue");
    useAnnotationStore.setState(INITIAL_ANNOTATION_STATE);
    resetAnnotationWriteQueue();
});

afterEach(() => {
    useMorphStore.setState(INITIAL_MORPH_STATE);
});

// jsdom lacks pointer capture, which the morph marker takes while it is dragged.
for (const name of ["setPointerCapture", "releasePointerCapture"] as const) {
    if (!(name in Element.prototype)) {
        Object.defineProperty(Element.prototype, name, { configurable: true, value: () => undefined });
    }
}

// jsdom lacks PointerEvent; a mouse event carrying a pointer id gives the marker's drag its coordinates.
if (!("PointerEvent" in window)) {
    class PointerEventStub extends MouseEvent {
        readonly pointerId: number;
        readonly pointerType: string;
        readonly isPrimary: boolean;

        constructor(type: string, init: PointerEventInit = {}) {
            super(type, init);
            this.pointerId = init.pointerId ?? 0;
            this.pointerType = init.pointerType ?? "mouse";
            this.isPrimary = init.isPrimary ?? true;
        }
    }

    vi.stubGlobal("PointerEvent", PointerEventStub);
}

// jsdom keeps localStorage across the tests of a file, which would carry a saved layout into the next shell.
afterEach(() => {
    localStorage.clear();
});

// jsdom lacks a canvas renderer; components handle a null 2D context, so tests take that path quietly.
vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

// jsdom logs a "not implemented" error for every play(), pause() and load() call; wavesurfer loads
// on creation and again as it is destroyed.
vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);

// jsdom lacks ResizeObserver, which dockview uses to fit its layout to its host element.
class ResizeObserverStub implements ResizeObserver {
    observe(): void {
        // no real layout to observe under jsdom
    }
    unobserve(): void {
        // no real layout to observe under jsdom
    }
    disconnect(): void {
        // no real layout to observe under jsdom
    }
}

vi.stubGlobal("ResizeObserver", ResizeObserverStub);

// jsdom lacks matchMedia, which useThemeSignal calls to follow the operating system's color scheme.
vi.stubGlobal("matchMedia", (media: string) => ({
    matches: false,
    media,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
}));

// jsdom lays nothing out, so offsetWidth and offsetHeight read 0, and the virtualized lists measure
// their scroll container through them on mount.
const STUBBED_ELEMENT_EXTENT_PX = 600;

Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get: () => STUBBED_ELEMENT_EXTENT_PX,
});
Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get: () => STUBBED_ELEMENT_EXTENT_PX,
});

// recharts' ResponsiveContainer sizes its chart from getBoundingClientRect on mount, which jsdom
// reads as an all-zero rect.
vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    width: STUBBED_ELEMENT_EXTENT_PX,
    height: STUBBED_ELEMENT_EXTENT_PX,
    top: 0,
    right: STUBBED_ELEMENT_EXTENT_PX,
    bottom: STUBBED_ELEMENT_EXTENT_PX,
    left: 0,
    toJSON: () => ({}),
});
