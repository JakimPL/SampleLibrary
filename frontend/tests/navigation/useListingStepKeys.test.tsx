import { act, fireEvent, render, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ShellView } from "../../src/navigation/shellView";
import { steppedHash, useListingStepKeys } from "../../src/navigation/useListingStepKeys";
import { useListingOrderStore } from "../../src/workspace/listingOrderStore";

const NEIGHBORS = { previous: "a", next: "c", position: 2, count: 3 };

function keyEvent(key: string, modifiers: Partial<KeyboardEventInit> = {}): KeyboardEvent {
    return new KeyboardEvent("keydown", { key, altKey: true, ...modifiers });
}

function StepKeys({ view }: { readonly view: ShellView }): ReactElement {
    useListingStepKeys(view);
    return <p>listening</p>;
}

function routerAt(path: string, view: ShellView): ReturnType<typeof createMemoryRouter> {
    const router = createMemoryRouter([{ path: "*", element: <StepKeys view={view} /> }], { initialEntries: [path] });
    render(<RouterProvider router={router} />);
    return router;
}

describe("steppedHash", () => {
    it("names the neighbor an Alt-arrow points at", () => {
        expect(steppedHash(keyEvent("ArrowRight"), NEIGHBORS)).toBe("c");
        expect(steppedHash(keyEvent("ArrowLeft"), NEIGHBORS)).toBe("a");
    });

    it("answers to nothing else", () => {
        expect(steppedHash(keyEvent("ArrowRight", { altKey: false }), NEIGHBORS)).toBeNull();
        expect(steppedHash(keyEvent("ArrowRight", { ctrlKey: true }), NEIGHBORS)).toBeNull();
        expect(steppedHash(keyEvent("ArrowDown"), NEIGHBORS)).toBeNull();
        expect(steppedHash(keyEvent("ArrowRight"), { ...NEIGHBORS, next: null })).toBeNull();
    });
});

describe("useListingStepKeys", () => {
    it("steps the shown sample through its listing, replacing the address", async () => {
        act(() => {
            useListingOrderStore.getState().publish("sample", ["a", "b", "c"]);
        });
        const router = routerAt("/samples/b", { kind: "sample", sampleHash: "b" });

        fireEvent.keyDown(window, { key: "ArrowRight", altKey: true });

        await waitFor(() => {
            expect(router.state.location.pathname).toBe("/samples/c");
        });
        expect(router.state.historyAction).toBe("REPLACE");
    });

    it("steps a module the same way", async () => {
        act(() => {
            useListingOrderStore.getState().publish("module", ["x", "y"]);
        });
        const router = routerAt("/modules/y", { kind: "module", moduleHash: "y" });

        fireEvent.keyDown(window, { key: "ArrowLeft", altKey: true });

        await waitFor(() => {
            expect(router.state.location.pathname).toBe("/modules/x");
        });
    });

    it("leaves a panel view where it is", async () => {
        act(() => {
            useListingOrderStore.getState().publish("sample", ["a", "b"]);
        });
        const router = routerAt("/cloud", { kind: "panel", panelId: "cloud" });

        fireEvent.keyDown(window, { key: "ArrowRight", altKey: true });

        await act(async () => {
            await Promise.resolve();
        });
        expect(router.state.location.pathname).toBe("/cloud");
    });
});
