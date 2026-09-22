import { describe, expect, it } from "vitest";

import { PLAYER_STRIP_STORAGE_KEY, usePlayerStripStore } from "../../../src/shell/player/playerStripStore";

describe("usePlayerStripStore", () => {
    it("keeps each change for the next visit", () => {
        usePlayerStripStore.getState().toggleExpanded();
        usePlayerStripStore.getState().setVisible(false);

        expect(JSON.parse(localStorage.getItem(PLAYER_STRIP_STORAGE_KEY) ?? "{}")).toEqual({
            visible: false,
            expanded: !usePlayerStripStore.getState().expanded ? false : true,
        });
    });

    it("flips the expansion and the visibility independently", () => {
        const before = usePlayerStripStore.getState();

        usePlayerStripStore.getState().toggleExpanded();
        expect(usePlayerStripStore.getState().expanded).toBe(!before.expanded);
        expect(usePlayerStripStore.getState().visible).toBe(before.visible);

        usePlayerStripStore.getState().setVisible(!before.visible);
        expect(usePlayerStripStore.getState().visible).toBe(!before.visible);
        expect(usePlayerStripStore.getState().expanded).toBe(!before.expanded);
    });
});
