import { describe, expect, it } from "vitest";

import { PANEL_REGISTRY } from "../../src/workspace/panelRegistry";

const definitions = Object.values(PANEL_REGISTRY);

describe("PANEL_REGISTRY", () => {
    it("keys every definition by its own id", () => {
        for (const [key, definition] of Object.entries(PANEL_REGISTRY)) {
            expect(definition.id).toBe(key);
        }
    });

    it("declares every reference panel before the panel placed beside it", () => {
        const seen = new Set<string>();
        for (const definition of definitions) {
            if (definition.placement !== null) {
                expect(seen.has(definition.placement.referencePanel)).toBe(true);
            }
            seen.add(definition.id);
        }
    });

    it("numbers the phone tabs from one without a gap", () => {
        const orders = definitions
            .flatMap((definition) => (definition.phone.kind === "tab" ? [definition.phone.order] : []))
            .sort((a, b) => a - b);

        expect(orders).toEqual(orders.map((_, index) => index + 1));
    });

    it("gives every address to one panel, with the root to the samples", () => {
        const paths = definitions.flatMap((definition) => (definition.path === null ? [] : [definition.path]));

        expect(new Set(paths).size).toBe(paths.length);
        expect(PANEL_REGISTRY["samples-list"].path).toBe("/");
    });

    it("keeps the cloud drawn while it is tabbed away", () => {
        expect(PANEL_REGISTRY.cloud.renderer).toBe("always");
    });
});
