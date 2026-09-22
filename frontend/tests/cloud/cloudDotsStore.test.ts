import { beforeEach, describe, expect, it, vi } from "vitest";

import { CLOUD_DOTS_STORAGE_KEY, isCloudDots } from "../../src/cloud/cloudDotsStore";

describe("useCloudDotsStore", () => {
    beforeEach(() => {
        vi.resetModules();
        localStorage.clear();
    });

    it("starts automatic, and keeps a choice of plain dots for the next visit", async () => {
        const { useCloudDotsStore } = await import("../../src/cloud/cloudDotsStore");
        expect(useCloudDotsStore.getState().dots).toBe("auto");

        useCloudDotsStore.getState().setDots("plain");

        expect(useCloudDotsStore.getState().dots).toBe("plain");
        expect(localStorage.getItem(CLOUD_DOTS_STORAGE_KEY)).toBe("plain");
    });

    it("reads the choice an earlier visit saved, and starts automatic from one it does not know", async () => {
        localStorage.setItem(CLOUD_DOTS_STORAGE_KEY, "plain");
        const saved = await import("../../src/cloud/cloudDotsStore");
        expect(saved.useCloudDotsStore.getState().dots).toBe("plain");

        vi.resetModules();
        localStorage.setItem(CLOUD_DOTS_STORAGE_KEY, "sideways");
        const unknown = await import("../../src/cloud/cloudDotsStore");
        expect(unknown.useCloudDotsStore.getState().dots).toBe("auto");
    });
});

describe("isCloudDots", () => {
    it("knows the two ways the points draw", () => {
        expect(isCloudDots("auto")).toBe(true);
        expect(isCloudDots("plain")).toBe(true);
        expect(isCloudDots("blurry")).toBe(false);
    });
});
