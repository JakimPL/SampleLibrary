import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../src/api/samples";
import { MorphHistory } from "../../src/morph/MorphHistory";
import { END_LETTERS, type MorphEnd, useMorphStore } from "../../src/morph/morphStore";
import { shortHash } from "../../src/shared/format";
import { useSelectionStore } from "../../src/workspace/selectionStore";

const A = "a".repeat(64);
const B = "b".repeat(64);
const C = "c".repeat(64);
const NAMES: Readonly<Record<string, string>> = { [A]: "kick_808", [B]: "snare_tight", [C]: "hat_closed" };

const { getSamplePreview } = vi.hoisted(() => ({ getSamplePreview: vi.fn() }));

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, getSamplePreview };
});

function serveNames(): void {
    getSamplePreview.mockImplementation((hash: string) =>
        Promise.resolve({ hash, display_name: NAMES[hash] ?? "", thumbnail: null, category: null, hand_label: null }),
    );
}

function column(end: MorphEnd): HTMLElement {
    return screen.getByRole("region", { name: END_LETTERS[end] });
}

function rowsOf(end: MorphEnd): HTMLElement[] {
    return within(column(end)).queryAllByRole("button");
}

async function row(end: MorphEnd, name: string): Promise<HTMLElement> {
    return within(column(end)).findByRole("button", { name });
}

function pressedIn(end: MorphEnd): readonly boolean[] {
    return rowsOf(end).map((button) => button.getAttribute("aria-pressed") === "true");
}

describe("MorphHistory with nothing held", () => {
    it("shows two empty columns with nothing to undo, redo or forget", () => {
        serveNames();
        render(<MorphHistory />);

        expect(rowsOf("first")).toHaveLength(0);
        expect(rowsOf("second")).toHaveLength(0);
        expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Redo" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Forget all" })).toBeDisabled();
    });
});

describe("MorphHistory with samples held", () => {
    it("lists each end's samples newest first, the one held now pressed", async () => {
        serveNames();
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setEnd("first", C);
        render(<MorphHistory />);

        const newest = await row("first", NAMES[C] ?? "");
        expect(rowsOf("first")[0]).toBe(newest);
        expect(await row("first", NAMES[A] ?? "")).toBe(rowsOf("first")[1]);
        expect(pressedIn("first")).toEqual([true, false]);
        expect(await row("second", NAMES[B] ?? "")).toHaveAttribute("aria-pressed", "true");
    });

    it("names a row by its short hash until the catalog answers", () => {
        getSamplePreview.mockReturnValue(new Promise(() => undefined));
        useMorphStore.getState().join(A, B);
        render(<MorphHistory />);

        expect(within(column("first")).getByRole("button", { name: shortHash(A) })).toBeInTheDocument();
    });

    /** One row picked from a column: the pair before, the row, and the pair after. */
    interface PickCase {
        readonly name: string;
        readonly prepare: () => void;
        readonly end: MorphEnd;
        readonly hash: string;
        readonly expected: { readonly first: string | null; readonly second: string | null };
    }

    const PICK_CASES: readonly PickCase[] = [
        {
            name: "gives a sample back to A from A's column",
            prepare: () => {
                useMorphStore.getState().join(A, B);
                useMorphStore.getState().setEnd("first", C);
            },
            end: "first",
            hash: A,
            expected: { first: A, second: B },
        },
        {
            name: "gives a sample back to B from B's column",
            prepare: () => {
                useMorphStore.getState().join(A, B);
                useMorphStore.getState().setEnd("second", C);
            },
            end: "second",
            hash: B,
            expected: { first: A, second: B },
        },
        {
            name: "trades the ends when the sample sits at the other end",
            prepare: () => {
                useMorphStore.getState().join(A, B);
                useMorphStore.getState().swap();
            },
            end: "first",
            hash: A,
            expected: { first: A, second: B },
        },
        {
            name: "leaves the pair as it is from the pressed row",
            prepare: () => {
                useMorphStore.getState().join(A, B);
            },
            end: "first",
            hash: A,
            expected: { first: A, second: B },
        },
    ];

    it.each(PICK_CASES)("$name, taking it in hand", async ({ prepare, end, hash, expected }: PickCase) => {
        serveNames();
        prepare();
        render(<MorphHistory />);

        fireEvent.click(await row(end, NAMES[hash] ?? ""));

        expect(useMorphStore.getState()).toMatchObject(expected);
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash });
        expect(await row(end, NAMES[hash] ?? "")).toHaveAttribute("aria-pressed", "true");
    });

    it("moves the pressed rows with undo and redo, the rows staying", async () => {
        serveNames();
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setEnd("first", C);
        render(<MorphHistory />);
        await row("first", NAMES[A] ?? "");

        fireEvent.click(screen.getByRole("button", { name: "Undo" }));
        expect(pressedIn("first")).toEqual([false, true]);
        expect(screen.getByRole("button", { name: "Redo" })).toBeEnabled();

        fireEvent.click(screen.getByRole("button", { name: "Redo" }));
        expect(pressedIn("first")).toEqual([true, false]);
        expect(screen.getByRole("button", { name: "Redo" })).toBeDisabled();
    });

    it("forgets every row but the ones held now", async () => {
        serveNames();
        useMorphStore.getState().join(A, B);
        useMorphStore.getState().setEnd("first", C);
        useMorphStore.getState().clearEnd("second");
        render(<MorphHistory />);
        await row("first", NAMES[A] ?? "");

        fireEvent.click(screen.getByRole("button", { name: "Forget all" }));

        expect(rowsOf("first")).toHaveLength(1);
        expect(rowsOf("first")[0]).toHaveAttribute("aria-pressed", "true");
        expect(rowsOf("second")).toHaveLength(0);
        expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled();
    });
});
