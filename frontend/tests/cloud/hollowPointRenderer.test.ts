import { describe, expect, it } from "vitest";

import { createHollowPointRenderer } from "../../src/cloud/hollowPointRenderer";

describe("createHollowPointRenderer", () => {
    it("answers null for a canvas that yields no WebGL context", () => {
        expect(createHollowPointRenderer(document.createElement("canvas"))).toBeNull();
    });
});
