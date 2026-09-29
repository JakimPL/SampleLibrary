import { describe, expect, it, vi } from "vitest";

import {
    type Held,
    HELD_CAPACITY,
    MORPH_ENDS,
    type MorphSnapshot,
    sameSnapshot,
    snapshotOf,
    UNDO_DEPTH,
} from "../../src/morph/morphHistory";
import { MORPH_HISTORY_STORAGE_KEY } from "../../src/morph/morphHistoryPersistence";
import { DEFAULT_WEIGHT, snapWeight, useMorphStore, WEIGHT_STEP } from "../../src/morph/morphStore";
import { choosePair } from "../support/morphPair";

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
    it("swaps the ends and mirrors the weight, so the audible point stays put", () => {
        choosePair(A, B);
        useMorphStore.getState().setWeight(0.25);

        useMorphStore.getState().swap();

        expect(useMorphStore.getState()).toMatchObject({ first: B, second: A, weight: 0.75 });
    });

    it("snaps every weight it is handed", () => {
        useMorphStore.getState().setWeight(0.304);

        expect(useMorphStore.getState().weight).toBe(0.3);
    });
});

describe("naming an end outright", () => {
    it("makes a sample the first end, and trades places with the second when it holds that sample", () => {
        choosePair("a", "b");

        useMorphStore.getState().setEnd("first", "c");
        expect(useMorphStore.getState()).toMatchObject({ first: "c", second: "b" });

        useMorphStore.getState().setEnd("first", "b");
        expect(useMorphStore.getState()).toMatchObject({ first: "b", second: "c" });
    });

    it("makes a sample the second end, and trades places with the first when it holds that sample", () => {
        choosePair("a", "b");

        useMorphStore.getState().setEnd("second", "c");
        expect(useMorphStore.getState()).toMatchObject({ first: "a", second: "c" });

        useMorphStore.getState().setEnd("second", "a");
        expect(useMorphStore.getState()).toMatchObject({ first: "c", second: "a" });
    });

    it("mirrors the weight when naming an end trades the two", () => {
        choosePair(A, B);
        useMorphStore.getState().setWeight(0.25);

        useMorphStore.getState().setEnd("first", B);

        expect(useMorphStore.getState()).toMatchObject({ first: B, second: A, weight: 0.75 });
    });

    it("names an end with the selection left where it was", () => {
        const { selectedEnd } = useMorphStore.getState();

        useMorphStore.getState().setEnd("second", A);

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: A, selectedEnd });
    });
});

describe("the render on screen", () => {
    const HEARD_WEIGHT = 0.1;
    const SLIDER_WEIGHT = 0.75;
    const MIRRORED_SLIDER_WEIGHT = 0.25;

    it("draws the slider's point as soon as the second end is chosen", () => {
        useMorphStore.getState().setEnd("first", A);
        expect(useMorphStore.getState().renderedWeight).toBeNull();

        useMorphStore.getState().setEnd("second", B);

        expect(useMorphStore.getState().renderedWeight).toBe(DEFAULT_WEIGHT);
    });

    it("records the weight a point was heard at, and keeps it while the pair stays", () => {
        choosePair(A, B);
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
            name: "the ends swap",
            change: () => {
                useMorphStore.getState().swap();
            },
            drawnAt: MIRRORED_SLIDER_WEIGHT,
        },
        {
            name: "the selected end takes a sample",
            change: () => {
                useMorphStore.getState().selectEnd("second");
                useMorphStore.getState().takeSample(C);
            },
            drawnAt: SLIDER_WEIGHT,
        },
    ];

    it.each(PAIR_CHANGES)("draws the slider's point afresh once $name", ({ change, drawnAt }: PairChange) => {
        choosePair(A, B);
        useMorphStore.getState().setWeight(HEARD_WEIGHT);
        useMorphStore.getState().markRendered();
        useMorphStore.getState().setWeight(SLIDER_WEIGHT);

        change();

        expect(useMorphStore.getState().renderedWeight).toBe(drawnAt);
    });
});

describe("the selected end", () => {
    it("stays on the end last selected, however often it is selected", () => {
        useMorphStore.getState().selectEnd("second");
        useMorphStore.getState().selectEnd("second");

        expect(useMorphStore.getState().selectedEnd).toBe("second");
    });

    it("fills an empty pair in the order samples are taken, the selection moving to the empty end", () => {
        useMorphStore.getState().selectEnd("first");

        useMorphStore.getState().takeSample(A);
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: null, selectedEnd: "second" });

        useMorphStore.getState().takeSample(B);
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: B, selectedEnd: "second" });
    });

    it("hands the selection to the first end when the second takes a sample with the first empty", () => {
        useMorphStore.getState().selectEnd("second");

        useMorphStore.getState().takeSample(A);

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: A, selectedEnd: "first" });
    });

    it("gives every sample taken to the selected end once the pair is whole, and stays selected", () => {
        choosePair(A, B);
        useMorphStore.getState().selectEnd("first");

        useMorphStore.getState().takeSample(C);

        expect(useMorphStore.getState()).toMatchObject({ first: C, second: B, selectedEnd: "first" });
    });

    /** A sample taken while the pair already holds it, which leaves the whole state as it stands. */
    interface HeldTakeCase {
        readonly name: string;
        readonly prepare: () => void;
        readonly hash: string;
    }

    const HELD_TAKE_CASES: readonly HeldTakeCase[] = [
        {
            name: "the selected end's own sample",
            prepare: () => {
                choosePair(A, B);
                useMorphStore.getState().selectEnd("first");
            },
            hash: A,
        },
        {
            name: "the other end's sample",
            prepare: () => {
                choosePair(A, B);
                useMorphStore.getState().selectEnd("first");
            },
            hash: B,
        },
        {
            name: "the sample just taken into an empty pair, as a double click's second click takes it",
            prepare: () => {
                useMorphStore.getState().selectEnd("first");
                useMorphStore.getState().takeSample(A);
            },
            hash: A,
        },
    ];

    it.each(HELD_TAKE_CASES)("leaves everything as it is on taking $name", ({ prepare, hash }: HeldTakeCase) => {
        prepare();
        const before = useMorphStore.getState();

        useMorphStore.getState().takeSample(hash);

        expect(useMorphStore.getState()).toBe(before);
    });

    it("keeps the selected letter through a swap", () => {
        choosePair(A, B);
        useMorphStore.getState().selectEnd("second");

        useMorphStore.getState().swap();

        expect(useMorphStore.getState()).toMatchObject({ first: B, second: A, selectedEnd: "second" });
    });
});

describe("undo and redo", () => {
    const D = "d".repeat(64);
    const MOVED_WEIGHT = 0.25;
    const MIRRORED_WEIGHT = 0.75;
    const BEFORE = { first: A, second: B, weight: MOVED_WEIGHT };

    /** One change to the pair, and how the pair stands once it has happened. */
    interface UndoCase {
        readonly name: string;
        readonly change: () => void;
        readonly after: Partial<MorphSnapshot>;
    }

    const UNDO_CASES: readonly UndoCase[] = [
        {
            name: "another end is named",
            change: () => {
                useMorphStore.getState().setEnd("second", C);
            },
            after: { first: A, second: C, weight: MOVED_WEIGHT },
        },
        {
            name: "the ends swap",
            change: () => {
                useMorphStore.getState().swap();
            },
            after: { first: B, second: A, weight: MIRRORED_WEIGHT },
        },
        {
            name: "an end is named with the other end's sample",
            change: () => {
                useMorphStore.getState().setEnd("first", B);
            },
            after: { first: B, second: A, weight: MIRRORED_WEIGHT },
        },
        {
            name: "the selected end takes a sample",
            change: () => {
                useMorphStore.getState().selectEnd("second");
                useMorphStore.getState().takeSample(C);
            },
            after: { first: A, second: C },
        },
    ];

    it.each(UNDO_CASES)(
        "returns to how the pair stood before $name, and forward again",
        ({ change, after }: UndoCase) => {
            choosePair(A, B);
            useMorphStore.getState().setWeight(MOVED_WEIGHT);

            change();
            expect(useMorphStore.getState()).toMatchObject(after);

            useMorphStore.getState().undo();
            expect(useMorphStore.getState()).toMatchObject(BEFORE);

            useMorphStore.getState().redo();
            expect(useMorphStore.getState()).toMatchObject(after);
        },
    );

    it("lets the changes undone go once a new one is made", () => {
        choosePair(A, B);
        useMorphStore.getState().setEnd("second", C);
        useMorphStore.getState().undo();

        useMorphStore.getState().setEnd("second", D);
        expect(useMorphStore.getState().future).toHaveLength(0);

        useMorphStore.getState().redo();
        expect(useMorphStore.getState()).toMatchObject({ first: A, second: D });
    });

    /** One action that moves nothing, and so records nothing. */
    interface NoOpCase {
        readonly name: string;
        readonly prepare: () => void;
        readonly change: () => void;
    }

    const NO_OP_CASES: readonly NoOpCase[] = [
        {
            name: "an end named with the sample it holds",
            prepare: () => {
                choosePair(A, B);
            },
            change: () => {
                useMorphStore.getState().setEnd("first", A);
            },
        },
        {
            name: "an empty pair swapped at the default weight",
            prepare: () => undefined,
            change: () => {
                useMorphStore.getState().swap();
            },
        },
        {
            name: "a sample taken that the pair already holds",
            prepare: () => {
                choosePair(A, B);
            },
            change: () => {
                useMorphStore.getState().takeSample(B);
            },
        },
    ];

    it.each(NO_OP_CASES)("records nothing for $name", ({ prepare, change }: NoOpCase) => {
        prepare();
        const { past, future, held } = useMorphStore.getState();

        change();

        expect(useMorphStore.getState().past).toBe(past);
        expect(useMorphStore.getState().future).toBe(future);
        expect(useMorphStore.getState().held).toBe(held);
    });

    it("leaves everything as it is with nothing to undo or redo", () => {
        const state = useMorphStore.getState();

        useMorphStore.getState().undo();
        expect(useMorphStore.getState()).toBe(state);

        useMorphStore.getState().redo();
        expect(useMorphStore.getState()).toBe(state);
    });

    it("keeps the selected end through undo and redo", () => {
        choosePair(A, B);
        useMorphStore.getState().selectEnd("second");
        useMorphStore.getState().setEnd("first", C);

        useMorphStore.getState().undo();
        expect(useMorphStore.getState().selectedEnd).toBe("second");

        useMorphStore.getState().redo();
        expect(useMorphStore.getState().selectedEnd).toBe("second");
    });

    it("brings the drawn point back as it was, under the slider where it was", () => {
        choosePair(A, B);
        useMorphStore.getState().setWeight(0.1);
        useMorphStore.getState().markRendered();
        useMorphStore.getState().setWeight(MIRRORED_WEIGHT);
        useMorphStore.getState().setEnd("first", C);
        expect(useMorphStore.getState().renderedWeight).toBe(MIRRORED_WEIGHT);

        useMorphStore.getState().undo();

        expect(useMorphStore.getState()).toMatchObject({ first: A, weight: MIRRORED_WEIGHT, renderedWeight: 0.1 });
    });

    it("keeps the line to its depth behind the present", () => {
        for (let step = 0; step <= UNDO_DEPTH; step += 1) {
            useMorphStore.getState().setEnd("first", step % 2 === 0 ? A : B);
        }

        expect(useMorphStore.getState().past).toHaveLength(UNDO_DEPTH);
    });
});

describe("the samples each end has held", () => {
    function savedHeld(): unknown {
        return JSON.parse(localStorage.getItem(MORPH_HISTORY_STORAGE_KEY) ?? "null");
    }

    it("remembers each end's samples, the newest arrival first", () => {
        choosePair(A, B);
        expect(useMorphStore.getState().held).toEqual({ first: [A], second: [B] });

        useMorphStore.getState().setEnd("first", C);

        expect(useMorphStore.getState().held).toEqual({ first: [C, A], second: [B] });
    });

    it("leaves a column as it is when its end takes a sample it knows", () => {
        choosePair(A, B);
        useMorphStore.getState().setEnd("first", C);
        const { held } = useMorphStore.getState();

        useMorphStore.getState().setEnd("first", A);

        expect(useMorphStore.getState()).toMatchObject({ first: A, held });
        expect(useMorphStore.getState().held).toBe(held);
    });

    it("remembers a swap as an arrival at both ends", () => {
        choosePair(A, B);

        useMorphStore.getState().swap();

        expect(useMorphStore.getState().held).toEqual({ first: [B, A], second: [A, B] });
    });

    it("keeps the columns through undoing", () => {
        choosePair(A, B);
        useMorphStore.getState().setEnd("first", C);
        const { held } = useMorphStore.getState();

        useMorphStore.getState().undo();
        useMorphStore.getState().undo();

        expect(useMorphStore.getState().held).toBe(held);
    });

    it("keeps the columns in the browser's storage as they change", () => {
        choosePair(A, B);
        expect(savedHeld()).toEqual({ first: [A], second: [B] });

        useMorphStore.getState().setEnd("second", C);

        expect(savedHeld()).toEqual({ first: [A], second: [C, B] });
    });

    it("forgets every sample but the ones the ends hold now", () => {
        choosePair(A, B);
        useMorphStore.getState().setEnd("first", C);
        const { past } = useMorphStore.getState();

        useMorphStore.getState().forgetHeld();

        expect(useMorphStore.getState().held).toEqual({ first: [C], second: [B] });
        expect(savedHeld()).toEqual({ first: [C], second: [B] });
        expect(useMorphStore.getState().past).toBe(past);
    });

    it("reads the columns an earlier visit saved", async () => {
        localStorage.setItem(MORPH_HISTORY_STORAGE_KEY, JSON.stringify({ first: [A], second: [] }));
        vi.resetModules();

        const fresh = await import("../../src/morph/morphStore");

        expect(fresh.useMorphStore.getState().held).toEqual({ first: [A], second: [] });
    });
});

describe("the history under a random walk of every action", () => {
    const HASH_COUNT = 60;
    const STEPS = 1500;
    const SEED = 20260928;
    const MODULUS = 2147483648;
    const MULTIPLIER = 1103515245;
    const INCREMENT = 12345;
    const HASHES: readonly string[] = Array.from({ length: HASH_COUNT }, (_, index) =>
        index.toString(16).padStart(64, "0"),
    );

    /** A linear congruential draw in [0, 1), so a failing walk can be run again. */
    function drawsFrom(seed: number): () => number {
        let value = seed;
        return (): number => {
            value = (value * MULTIPLIER + INCREMENT) % MODULUS;
            return value / MODULUS;
        };
    }

    function pick<T>(draw: () => number, items: readonly T[]): T {
        const item = items[Math.floor(draw() * items.length)];
        if (item === undefined) {
            throw new Error("nothing to pick from");
        }
        return item;
    }

    interface Step {
        readonly name: string;
        readonly run: (draw: () => number) => void;
    }

    /** The actions that change the ends and so record a snapshot; the rest move the slider, the mark or the selection alone. */
    const RECORDING_KINDS: ReadonlySet<string> = new Set(["setEnd", "swap", "takeSample"]);

    const STEP_KINDS: readonly Step[] = [
        {
            name: "setEnd",
            run: (draw) => {
                useMorphStore.getState().setEnd(pick(draw, MORPH_ENDS), pick(draw, HASHES));
            },
        },
        {
            name: "swap",
            run: () => {
                useMorphStore.getState().swap();
            },
        },
        {
            name: "takeSample",
            run: (draw) => {
                useMorphStore.getState().takeSample(pick(draw, HASHES));
            },
        },
        {
            name: "selectEnd",
            run: (draw) => {
                useMorphStore.getState().selectEnd(pick(draw, MORPH_ENDS));
            },
        },
        {
            name: "setWeight",
            run: (draw) => {
                useMorphStore.getState().setWeight(draw());
            },
        },
        {
            name: "markRendered",
            run: () => {
                useMorphStore.getState().markRendered();
            },
        },
        {
            name: "undo",
            run: () => {
                useMorphStore.getState().undo();
            },
        },
        {
            name: "redo",
            run: () => {
                useMorphStore.getState().redo();
            },
        },
        {
            name: "forgetHeld",
            run: () => {
                useMorphStore.getState().forgetHeld();
            },
        },
    ];

    /** The column grew at the top alone: its new rows lead, and the rows it had follow in their order, the tail let go at most. */
    function expectGrownAtTop(before: readonly string[], after: readonly string[]): void {
        if (before === after) {
            return;
        }
        const arrivals = after.findIndex((hash) => before.includes(hash));
        const kept = arrivals === -1 ? 0 : after.length - arrivals;
        expect(arrivals === -1 ? after.length : arrivals).toBeGreaterThanOrEqual(1);
        expect(after.slice(after.length - kept)).toEqual(before.slice(0, kept));
        expect(after.length).toBeLessThanOrEqual(HELD_CAPACITY);
    }

    function expectColumnsSound(held: Held, pair: MorphSnapshot): void {
        for (const end of MORPH_ENDS) {
            const column = held[end];
            expect(new Set(column).size).toBe(column.length);
            expect(column.length).toBeLessThanOrEqual(HELD_CAPACITY);
            const sample = pair[end];
            if (sample !== null) {
                expect(column).toContain(sample);
            }
        }
    }

    it("keeps every column, the line and the marks sound after each step", () => {
        const draw = drawsFrom(SEED);

        for (let step = 0; step < STEPS; step += 1) {
            const kind = pick(draw, STEP_KINDS);
            const before = useMorphStore.getState();

            kind.run(draw);
            const after = useMorphStore.getState();

            expectColumnsSound(after.held, after);
            expect(MORPH_ENDS).toContain(after.selectedEnd);
            if (kind.name !== "forgetHeld") {
                for (const end of MORPH_ENDS) {
                    expectGrownAtTop(before.held[end], after.held[end]);
                }
            }
            expect(after.past.length).toBeLessThanOrEqual(UNDO_DEPTH);
            expect(after.past.length + after.future.length).toBeLessThanOrEqual(UNDO_DEPTH);
            if (RECORDING_KINDS.has(kind.name) && !sameSnapshot(before, after)) {
                expect(after.future).toHaveLength(0);
                expect(after.past.at(-1)).toEqual(snapshotOf(before));
            } else if (kind.name !== "undo" && kind.name !== "redo") {
                expect(after.past).toBe(before.past);
                expect(after.future).toBe(before.future);
            }
            if (kind.name === "undo" || kind.name === "redo" || kind.name === "forgetHeld") {
                expect(after.selectedEnd).toBe(before.selectedEnd);
            }

            if (after.past.length > 0) {
                useMorphStore.getState().undo();
                useMorphStore.getState().redo();
                const back = useMorphStore.getState();
                expect(snapshotOf(back)).toEqual(snapshotOf(after));
                expect(back.past).toEqual(after.past);
                expect(back.future).toEqual(after.future);
                expect(back.selectedEnd).toBe(after.selectedEnd);
                expectColumnsSound(back.held, back);
            }
        }
    });
});
