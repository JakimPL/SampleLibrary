import type { SerializedDockview } from "dockview-react";
import { describe, expect, it } from "vitest";

import { buildDefaultLayout, defaultSerializedLayout } from "../../src/workspace/defaultLayout";
import { PANEL_REGISTRY } from "../../src/workspace/panelRegistry";
import { FakeDockviewApi } from "../support/fakeDockviewApi";

type GridNode = SerializedDockview["grid"]["root"];

interface Leaf {
    readonly id: string;
    readonly views: readonly string[];
    readonly activeView: string | undefined;
    readonly size: number | undefined;
}

function leavesOf(node: GridNode): Leaf[] {
    const { data } = node;
    if (Array.isArray(data)) {
        return data.flatMap(leavesOf);
    }
    return [{ id: data.id, views: data.views, activeView: data.activeView, size: node.size }];
}

describe("defaultSerializedLayout", () => {
    const layout = defaultSerializedLayout();
    const leaves = leavesOf(layout.grid.root);

    it("places every registered panel exactly once", () => {
        const placed = leaves.flatMap((leaf) => leaf.views).sort();

        expect(placed).toEqual(Object.keys(PANEL_REGISTRY).sort());
    });

    it("puts the first tab of every group in front", () => {
        for (const leaf of leaves) {
            expect(leaf.activeView).toBe(leaf.views[0]);
        }
    });

    it("names every group once and starts on one of them", () => {
        const ids = leaves.map((leaf) => leaf.id);

        expect(new Set(ids).size).toBe(ids.length);
        expect(ids).toContain(layout.activeGroup);
    });

    it("gives every group a size inside the box", () => {
        for (const leaf of leaves) {
            expect(leaf.size).toBeGreaterThan(0);
            expect(leaf.size).toBeLessThanOrEqual(Math.max(layout.grid.width, layout.grid.height));
        }
    });

    it("describes every panel by its component and its renderer", () => {
        for (const definition of Object.values(PANEL_REGISTRY)) {
            expect(layout.panels[definition.id]).toEqual({
                id: definition.id,
                contentComponent: definition.id,
                title: definition.title,
                renderer: definition.renderer,
            });
        }
    });
});

describe("buildDefaultLayout", () => {
    it("hands the arrangement to dockview whole", () => {
        const api = new FakeDockviewApi([]);

        buildDefaultLayout(api.asApi());

        expect(api.fromJSON).toHaveBeenCalledWith(defaultSerializedLayout());
    });
});
