import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { clearRequestCache } from "../src/shared/requestCache";
import { DEFAULT_THEME_PREFERENCE } from "../src/theme/themeOptions";
import { useThemeStore } from "../src/theme/themeStore";
import { INITIAL_SELECTION_STATE, useSelectionStore } from "../src/workspace/selectionStore";

afterEach(() => {
    cleanup();
});

// selectionStore is a module-level singleton read and written by every panel's own tests, so it is
// reset unconditionally here rather than relying on each test file to remember a unique fixture.
afterEach(() => {
    useSelectionStore.setState(INITIAL_SELECTION_STATE);
});

// themeStore is likewise a module-level singleton, and every test that renders WorkspaceShell
// touches it through ThemeMenu; reset both the store and the DOM attribute it drives directly
// (not through setPreference) so this cleanup never re-writes the localStorage entry the hook
// below is about to clear anyway.
afterEach(() => {
    useThemeStore.setState({ preference: DEFAULT_THEME_PREFERENCE });
    delete document.documentElement.dataset.theme;
});

// requestCache is likewise a module-level singleton; without a reset, a cache key reused across
// test files would silently seed a later test's fetch with an earlier test's cached result.
afterEach(() => {
    clearRequestCache();
});

// jsdom's localStorage persists across tests in the same file; without clearing it, a test that
// exercises the shell's own layout persistence (closing/reopening a panel) would leak a saved
// layout into every test that mounts WorkspaceShell afterwards.
afterEach(() => {
    localStorage.clear();
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

// jsdom never computes real layout, so every element's offsetWidth/offsetHeight reads 0. The
// virtualized list panels measure their scroll container this way on mount, before the
// ResizeObserver stub above could ever report a real size, so a fixed nonzero measurement is
// stubbed globally here rather than only where a test happens to touch a virtualized table.
const STUBBED_ELEMENT_EXTENT_PX = 600;

Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get: () => STUBBED_ELEMENT_EXTENT_PX,
});
Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get: () => STUBBED_ELEMENT_EXTENT_PX,
});

// jsdom's getBoundingClientRect always reads an all-zero rect. recharts' ResponsiveContainer reads
// it once synchronously on mount to size its chart, before its ResizeObserver-driven updates could
// ever take over (the stub above is a no-op), so a real chart panel would otherwise measure zero
// and render nothing.
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
