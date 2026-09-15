import { describe, expect, it } from "vitest";

import { DEFAULT_WEIGHT, snapWeight, useMorphStore, WEIGHT_STEP } from "../../src/morph/morphStore";

const A = "a".repeat(64);
const B = "b".repeat(64);
const C = "c".repeat(64);

describe("snapWeight", () => {
    it("holds a weight to the unit interval and to the grid of sixteenths", () => {
        expect(snapWeight(0.3)).toBe(0.3125);
        expect(snapWeight(-0.4)).toBe(0);
        expect(snapWeight(1.7)).toBe(1);
        expect(snapWeight(WEIGHT_STEP * 5)).toBe(WEIGHT_STEP * 5);
    });
});

describe("morphStore", () => {
    it("joins the anchor as the first end and the chosen sample as the second", () => {
        useMorphStore.getState().join(A, B);

        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B });
    });

    it("opens a pair with the chosen sample when nothing anchors it, and closes it on the next", () => {
        useMorphStore.getState().join(null, A);
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: null });

        useMorphStore.getState().join(null, B);
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B });
    });

    it("leaves a pair alone when the anchor and the chosen sample are one", () => {
        useMorphStore.getState().join(A, B);

        useMorphStore.getState().join(C, C);

        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B });
    });

    it("swaps the ends and mirrors the weight, so the audible point stays put", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setWeight(0.25);

        useMorphStore.getState().swap();

        expect(useMorphStore.getState()).toMatchObject({ first: B, second: A, weight: 0.75 });
    });

    it("snaps every weight it is handed", () => {
        useMorphStore.getState().setWeight(0.3);

        expect(useMorphStore.getState().weight).toBe(0.3125);
    });

    it("clears the pair and returns the weight to its default", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setWeight(0.75);

        useMorphStore.getState().clear();

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null, weight: DEFAULT_WEIGHT });
    });
});
