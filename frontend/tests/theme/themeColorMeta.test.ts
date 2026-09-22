import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { syncThemeColorMeta, useThemeColorMeta } from "../../src/theme/themeColorMeta";
import { useThemeStore } from "../../src/theme/themeStore";

function installMetas(): readonly HTMLMetaElement[] {
    const metas = ["(prefers-color-scheme: light)", "(prefers-color-scheme: dark)"].map((media) => {
        const meta = document.createElement("meta");
        meta.name = "theme-color";
        meta.media = media;
        meta.content = "#ffffff";
        document.head.appendChild(meta);
        return meta;
    });
    return metas;
}

function styleReporting(color: string): void {
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
        getPropertyValue: () => color,
    } as unknown as CSSStyleDeclaration);
}

describe("syncThemeColorMeta", () => {
    afterEach(() => {
        vi.restoreAllMocks();
        document.head.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
            meta.remove();
        });
    });

    it("writes the applied bar color into every theme-color meta", () => {
        const metas = installMetas();
        styleReporting(" #232a35 ");

        syncThemeColorMeta();

        expect(metas.map((meta) => meta.content)).toEqual(["#232a35", "#232a35"]);
    });

    it("leaves the metas as they were while the token is unknown", () => {
        const metas = installMetas();
        styleReporting("");

        syncThemeColorMeta();

        expect(metas.map((meta) => meta.content)).toEqual(["#ffffff", "#ffffff"]);
    });

    it("follows the theme preference as it changes", () => {
        const metas = installMetas();
        styleReporting("#e9ebf0");
        renderHook(() => {
            useThemeColorMeta();
        });
        expect(metas[0]?.content).toBe("#e9ebf0");
        styleReporting("#232a35");

        act(() => {
            useThemeStore.getState().setPreference("dark");
        });

        expect(metas[0]?.content).toBe("#232a35");
    });
});
