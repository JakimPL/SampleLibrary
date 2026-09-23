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

        useMorphStore.getState().setEnd("first", "c");
        expect(useMorphStore.getState()).toMatchObject({ first: "c", second: "b" });

        useMorphStore.getState().setEnd("first", "b");
        expect(useMorphStore.getState()).toMatchObject({ first: "b", second: null });
    });

    it("makes a sample the second end and keeps the first unless it is the same sample", () => {
        useMorphStore.getState().join("a", "b");

        useMorphStore.getState().setEnd("second", "c");
        expect(useMorphStore.getState()).toMatchObject({ first: "a", second: "c" });

        useMorphStore.getState().setEnd("second", "a");
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: "a" });
    });

    it("names an end with the selection left where it was", () => {
        useMorphStore.getState().setEnd("second", A);

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: A, selectedEnd: null });
    });

    it("lets one end go and keeps the other", () => {
        useMorphStore.getState().join(A, B);

        useMorphStore.getState().clearEnd("first");
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: B });

        useMorphStore.getState().setEnd("first", A);
        useMorphStore.getState().clearEnd("second");
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: null });
    });
});

describe("the render on screen", () => {
    const HEARD_WEIGHT = 0.1;
    const SLIDER_WEIGHT = 0.75;
    const MIRRORED_SLIDER_WEIGHT = 0.25;

    it("draws the slider's point as soon as the second end is chosen", () => {
        useMorphStore.getState().join(null, A);
        expect(useMorphStore.getState().renderedWeight).toBeNull();

        useMorphStore.getState().join(null, B);

        expect(useMorphStore.getState().renderedWeight).toBe(DEFAULT_WEIGHT);
    });

    it("records the weight a point was heard at, and keeps it while the pair stays", () => {
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setWeight(0.25);

        useMorphStore.getState().markRendered();
        expect(useMorphStore.getState().renderedWeight).toBe(0.25);

        useMorphStore.getState().setWeight(0.75);
        useMorphStore.getState().setEnd("first", A);
        expect(useMorphStore.getState().renderedWeight).toBe(0.25);
    });

    /** One change to the pair, and the point drawn once it has happened: the slider's own, or none. */
    interface PairChange {
        readonly name: string;
        readonly change: () => void;
        readonly drawnAt: number | null;
    }

    const PAIR_CHANGES: readonly PairChange[] = [
        {
            name: "another end is named",
            change: () => {
                useMorphStore.getState().setEnd("second", C);
            },
            drawnAt: SLIDER_WEIGHT,
        },
        {
            name: "the anchor joins a new sample",
            change: () => {
                useMorphStore.getState().join(A, C);
            },
            drawnAt: SLIDER_WEIGHT,
        },
        {
            name: "the ends swap",
            change: () => {
                useMorphStore.getState().swap();
            },
            drawnAt: MIRRORED_SLIDER_WEIGHT,
        },
        {
            name: "an end is let go",
            change: () => {
                useMorphStore.getState().clearEnd("first");
            },
            drawnAt: null,
        },
        {
            name: "the pair clears",
            change: () => {
                useMorphStore.getState().clear();
            },
            drawnAt: null,
        },
        {
            name: "the selected end takes a sample",
            change: () => {
                useMorphStore.getState().toggleSelectedEnd("second");
                useMorphStore.getState().takeSample(C);
            },
            drawnAt: SLIDER_WEIGHT,
        },
    ];

    it.each(PAIR_CHANGES)(
        "draws the slider's point afresh, or nothing, once $name",
        ({ change, drawnAt }: PairChange) => {
            useMorphStore.getState().join(A, B);
            useMorphStore.getState().setWeight(HEARD_WEIGHT);
            useMorphStore.getState().markRendered();
            useMorphStore.getState().setWeight(SLIDER_WEIGHT);

            change();

            expect(useMorphStore.getState().renderedWeight).toBe(drawnAt);
        },
    );
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
