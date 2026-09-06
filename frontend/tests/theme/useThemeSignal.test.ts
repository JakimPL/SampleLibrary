import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useThemeStore } from "../../src/theme/themeStore";
import { useThemeSignal } from "../../src/theme/useThemeSignal";

describe("useThemeSignal", () => {
    it("reports the store's current preference", () => {
        useThemeStore.getState().setPreference("dark");

        const { result } = renderHook(() => useThemeSignal());

        expect(result.current.preference).toBe("dark");
    });

    it("updates the reported preference as the store changes", () => {
        const { result } = renderHook(() => useThemeSignal());

        act(() => {
            useThemeStore.getState().setPreference("openmpt");
        });

        expect(result.current.preference).toBe("openmpt");
    });

    it("bumps systemVersion when the operating system's color scheme changes", () => {
        let changeListener: (() => void) | undefined;
        vi.spyOn(window, "matchMedia").mockReturnValue({
            matches: false,
            media: "(prefers-color-scheme: dark)",
            addEventListener: (_event: string, listener: () => void) => {
                changeListener = listener;
            },
            removeEventListener: () => undefined,
        } as unknown as MediaQueryList);

        const { result } = renderHook(() => useThemeSignal());
        const initialVersion = result.current.systemVersion;

        act(() => {
            changeListener?.();
        });

        expect(result.current.systemVersion).toBe(initialVersion + 1);
    });
});
