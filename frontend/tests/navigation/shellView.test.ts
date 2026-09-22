import { describe, expect, it } from "vitest";

import { shellViewOf } from "../../src/navigation/shellView";

describe("shellViewOf", () => {
    it("passes a panel view through untouched", () => {
        const routeView = { kind: "panel", panelId: "cloud" } as const;

        expect(shellViewOf(routeView, {})).toBe(routeView);
    });

    it("fills an entity view with the address's hash", () => {
        expect(shellViewOf({ kind: "sample" }, { sampleHash: "abc" })).toEqual({ kind: "sample", sampleHash: "abc" });
        expect(shellViewOf({ kind: "module" }, { moduleHash: "def" })).toEqual({ kind: "module", moduleHash: "def" });
    });

    it("refuses an entity route that arrived without its hash", () => {
        expect(() => shellViewOf({ kind: "sample" }, {})).toThrow("without a sample hash");
        expect(() => shellViewOf({ kind: "module" }, { sampleHash: "abc" })).toThrow("without a module hash");
    });
});
