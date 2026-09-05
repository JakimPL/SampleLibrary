import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
    cleanup();
});

// jsdom has no real canvas renderer; components must already treat a null 2D context as normal
// (see CloudPage), so tests exercise that path directly instead of jsdom's own noisy warning.
vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);

// jsdom has no real media pipeline either; play()/pause() are not implemented and jsdom logs a
// noisy "not implemented" error for each call, so both are stubbed the same way as getContext.
vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
