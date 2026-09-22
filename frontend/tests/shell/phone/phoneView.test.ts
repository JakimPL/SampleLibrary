import { describe, expect, it } from "vitest";

import { overflowPanels, phonePageOf, tabOf, tabOfPath, tabPanels } from "../../../src/shell/phone/phoneView";

describe("tabPanels", () => {
    it("lists the three tabs in their registered order, each at its own address", () => {
        expect(tabPanels().map((tab) => [tab.id, tab.path])).toEqual([
            ["samples-list", "/"],
            ["cloud", "/cloud"],
            ["modules-list", "/modules"],
        ]);
    });
});

describe("overflowPanels", () => {
    it("lists the panels the screen menu offers", () => {
        expect(overflowPanels().map((panel) => panel.id)).toEqual(["stats"]);
    });
});

describe("phonePageOf", () => {
    it("opens an entity as a page", () => {
        expect(phonePageOf({ kind: "sample", sampleHash: "abc" })).toEqual({ kind: "sample", sampleHash: "abc" });
        expect(phonePageOf({ kind: "module", moduleHash: "def" })).toEqual({ kind: "module", moduleHash: "def" });
    });

    it("shows a tab's panel on its tab and any other panel as a page", () => {
        expect(phonePageOf({ kind: "panel", panelId: "cloud" })).toBeNull();
        expect(phonePageOf({ kind: "panel", panelId: "stats" })).toEqual({ kind: "panel", panelId: "stats" });
    });
});

describe("tabOf and tabOfPath", () => {
    const tabs = tabPanels();

    it("finds the tab a view or an address names", () => {
        expect(tabOf(tabs, { kind: "panel", panelId: "modules-list" })?.id).toBe("modules-list");
        expect(tabOfPath(tabs, "/cloud")?.id).toBe("cloud");
    });

    it("finds none for a page or an address no tab answers", () => {
        expect(tabOf(tabs, { kind: "sample", sampleHash: "abc" })).toBeNull();
        expect(tabOf(tabs, { kind: "panel", panelId: "stats" })).toBeNull();
        expect(tabOfPath(tabs, "/stats")).toBeNull();
    });
});
