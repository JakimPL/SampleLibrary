import { describe, expect, it } from "vitest";

import { DEFAULT_WEIGHT, snapWeight, useMorphStore, WEIGHT_STEP } from "../../src/morph/morphStore";

const A = "a".repeat(64);
const B = "b".repeat(64);
const C = "c".repeat(64);

describe("snapWeight", () => {
    it("holds a weight to the unit interval and to the grid of hundredths", () => {
        expect(snapWeight(0.304)).toBe(0.3);
        expect(snapWeight(0.305)).toBe(0.31);
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
        useMorphStore.getState().setWeight(0.304);

        expect(useMorphStore.getState().weight).toBe(0.3);
    });

    it("clears the pair and returns the weight to its default", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setWeight(0.75);

        useMorphStore.getState().clear();

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null, weight: DEFAULT_WEIGHT });
    });
});

describe("naming an end outright", () => {
    it("makes a sample the first end and keeps the second unless it is the same sample", () => {
        useMorphStore.getState().join("a", "b");

        useMorphStore.getState().setFirst("c");
        expect(useMorphStore.getState()).toMatchObject({ first: "c", second: "b" });

        useMorphStore.getState().setFirst("b");
        expect(useMorphStore.getState()).toMatchObject({ first: "b", second: null });
    });

    it("makes a sample the second end and keeps the first unless it is the same sample", () => {
        useMorphStore.getState().join("a", "b");

        useMorphStore.getState().setSecond("c");
        expect(useMorphStore.getState()).toMatchObject({ first: "a", second: "c" });

        useMorphStore.getState().setSecond("a");
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: "a" });
    });

    it("lets one end go and keeps the other", () => {
        useMorphStore.getState().join(A, B);

        useMorphStore.getState().clearEnd("first");
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: B });

        useMorphStore.getState().setFirst(A);
        useMorphStore.getState().clearEnd("second");
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: null });
    });
});

describe("the render on screen", () => {
    it("records the weight a point was heard at, and keeps it while the pair stays", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setWeight(0.25);

        useMorphStore.getState().markRendered();
        expect(useMorphStore.getState().renderedWeight).toBe(0.25);

        useMorphStore.getState().setWeight(0.75);
        useMorphStore.getState().setFirst(A);
        expect(useMorphStore.getState().renderedWeight).toBe(0.25);
    });

    interface PairChange {
        readonly name: string;
        readonly change: () => void;
    }

    const PAIR_CHANGES: readonly PairChange[] = [
        {
            name: "another end is named",
            change: () => {
                useMorphStore.getState().setSecond(C);
            },
        },
        {
            name: "the anchor joins a new sample",
            change: () => {
                useMorphStore.getState().join(A, C);
            },
        },
        {
            name: "the ends swap",
            change: () => {
                useMorphStore.getState().swap();
            },
        },
        {
            name: "an end is let go",
            change: () => {
                useMorphStore.getState().clearEnd("first");
            },
        },
        {
            name: "the pair clears",
            change: () => {
                useMorphStore.getState().clear();
            },
        },
        {
            name: "the selected end takes a sample",
            change: () => {
                useMorphStore.getState().toggleSelectedEnd("second");
                useMorphStore.getState().takeSample(C);
            },
        },
    ];

    it.each(PAIR_CHANGES)("drops the render once $name", ({ change }: PairChange) => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().markRendered();

        change();

        expect(useMorphStore.getState().renderedWeight).toBeNull();
    });
});

describe("the selected end", () => {
    it("selects an end, moves to the other, and lets go on a second toggle", () => {
        useMorphStore.getState().toggleSelectedEnd("first");
        expect(useMorphStore.getState().selectedEnd).toBe("first");

        useMorphStore.getState().toggleSelectedEnd("second");
        expect(useMorphStore.getState().selectedEnd).toBe("second");

        useMorphStore.getState().toggleSelectedEnd("second");
        expect(useMorphStore.getState().selectedEnd).toBeNull();
    });

    it("gives the selected end every sample taken, and stays selected", () => {
        useMorphStore.getState().toggleSelectedEnd("first");

        useMorphStore.getState().takeSample(A);
        useMorphStore.getState().takeSample(B);

        expect(useMorphStore.getState()).toMatchObject({ first: B, second: null, selectedEnd: "first" });
    });

    it("takes nothing while no end is selected", () => {
        useMorphStore.getState().join(A, B);

        useMorphStore.getState().takeSample(C);

        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B, selectedEnd: null });
    });

    it("leaves the pair and its render alone when the selected end takes its own sample", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().markRendered();
        useMorphStore.getState().toggleSelectedEnd("first");

        useMorphStore.getState().takeSample(A);

        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B, renderedWeight: DEFAULT_WEIGHT });
    });

    it("trades the ends, with the weight mirrored, when the selected end takes the other end's sample", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setWeight(0.25);
        useMorphStore.getState().toggleSelectedEnd("first");

        useMorphStore.getState().takeSample(B);

        expect(useMorphStore.getState()).toMatchObject({ first: B, second: A, weight: 0.75, selectedEnd: "first" });
    });

    it("keeps the selected letter through a swap and through letting an end go, and drops it with the pair", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().toggleSelectedEnd("second");

        useMorphStore.getState().swap();
        expect(useMorphStore.getState().selectedEnd).toBe("second");

        useMorphStore.getState().clearEnd("second");
        expect(useMorphStore.getState()).toMatchObject({ first: B, second: null, selectedEnd: "second" });

        useMorphStore.getState().clear();
        expect(useMorphStore.getState().selectedEnd).toBeNull();
    });
});
