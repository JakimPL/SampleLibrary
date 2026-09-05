import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { INITIAL_SELECTION_STATE, useSelectionStore } from "../src/workspace/selectionStore";

afterEach(() => {
    cleanup();
});

// selectionStore is a module-level singleton read and written by every panel's own tests, so it is
// reset unconditionally here rather than relying on each test file to remember a unique fixture.
afterEach(() => {
    useSelectionStore.setState(INITIAL_SELECTION_STATE);
});

// jsdom has no real canvas renderer; components must already treat a null 2D context as normal
// (see CloudView), so tests exercise that path directly instead of jsdom's own noisy warning.
vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

// jsdom has no real media pipeline either; play()/pause() are not implemented and jsdom logs a
// noisy "not implemented" error for each call, so both are stubbed the same way as getContext.
vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);

// jsdom does not implement ResizeObserver, which dockview uses to auto-fit its layout to its host
// element; a no-op stub is enough for the shell to mount under a test's fixed jsdom viewport.
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
