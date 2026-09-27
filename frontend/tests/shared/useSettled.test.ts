import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSettled } from "../../src/shared/useSettled";

describe("useSettled", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("settles on a key that rests, and none a sweep passes over", () => {
        const { result, rerender } = renderHook(({ key }) => useSettled(key, 120), { initialProps: { key: "a" } });

        act(() => {
            vi.advanceTimersByTime(60);
        });
        rerender({ key: "b" });
        act(() => {
            vi.advanceTimersByTime(60);
        });
        expect(result.current).toBe(false);

        act(() => {
            vi.advanceTimersByTime(60);
        });
        expect(result.current).toBe(true);
    });
});
