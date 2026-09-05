import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
    cleanup();
});

// jsdom has no real canvas renderer; components must already treat a null 2D context as normal
// (see CloudPage), so tests exercise that path directly instead of jsdom's own noisy warning.
vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
