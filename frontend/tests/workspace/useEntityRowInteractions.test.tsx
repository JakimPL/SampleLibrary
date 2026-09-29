import { act, render, renderHook, screen } from "@testing-library/react";
import type { KeyboardEvent, MouseEvent, ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useMorphStore } from "../../src/morph/morphStore";
import { ROW_LINK_ATTRIBUTE } from "../../src/workspace/rowLinks";
import { useSelectionStore } from "../../src/workspace/selectionStore";
import { useEntityRowInteractions } from "../../src/workspace/useEntityRowInteractions";

function wrapper({ children }: { children: ReactNode }): ReactElement {
    return (
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<>{children}</>} />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
                <Route path="/modules/:moduleHash" element={<p>module route</p>} />
            </Routes>
        </MemoryRouter>
    );
}

interface FakeMouseEvent {
    readonly event: MouseEvent;
    readonly preventDefault: ReturnType<typeof vi.fn>;
}

function fakeMouseEvent(
    overrides: Partial<Record<"button" | "ctrlKey" | "shiftKey" | "detail", number | boolean>> = {},
    target: EventTarget | null = null,
): FakeMouseEvent {
    const preventDefault = vi.fn();
    const event = {
        button: 0,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        altKey: false,
        detail: 1,
        target,
        preventDefault,
        ...overrides,
    } as unknown as MouseEvent;
    return { event, preventDefault };
}

function fakeKeyEvent(key: string, currentTarget: HTMLElement): KeyboardEvent<HTMLElement> {
    return { key, currentTarget, preventDefault: vi.fn() } as unknown as KeyboardEvent<HTMLElement>;
}

describe("useEntityRowInteractions", () => {
    it("exposes the entity's own route as href", () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });

        expect(result.current.href).toBe("/samples/abc");
    });

    it("a plain click highlights the entity and prevents the default navigation", () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
        const { event, preventDefault } = fakeMouseEvent();

        act(() => {
            result.current.onClick(event);
        });

        expect(preventDefault).toHaveBeenCalled();
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "abc" });
    });

    it("a plain click on a sample gives it to the selected end of the morph", () => {
        useMorphStore.getState().selectEnd("second");
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });

        act(() => {
            result.current.onClick(fakeMouseEvent().event);
        });

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: "abc" });
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "abc" });
    });

    it("a plain click on a module leaves the pair empty", () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "module", hash: "def" }), { wrapper });

        act(() => {
            result.current.onClick(fakeMouseEvent().event);
        });

        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null });
    });

    it.each(["ctrlKey", "shiftKey"] as const)(
        "a click with %s is left alone, neither highlighting, filling the pair nor preventing the default navigation",
        (modifier) => {
            const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
            const { event, preventDefault } = fakeMouseEvent({ [modifier]: true });

            act(() => {
                result.current.onClick(event);
            });

            expect(preventDefault).not.toHaveBeenCalled();
            expect(useSelectionStore.getState().highlighted).toBeNull();
            expect(useMorphStore.getState()).toMatchObject({ first: null, second: null });
        },
    );

    it("a click a key press raised is left to the link, so Enter opens the entity", () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
        const { event, preventDefault } = fakeMouseEvent({ detail: 0 });

        act(() => {
            result.current.onClick(event);
        });

        expect(preventDefault).not.toHaveBeenCalled();
        expect(useSelectionStore.getState().highlighted).toBeNull();
    });

    it("a click on a control that opens the entity is left to that control", () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
        const control = document.createElement("a");
        control.setAttribute(ROW_LINK_ATTRIBUTE, "");
        const { event, preventDefault } = fakeMouseEvent({}, control);

        act(() => {
            result.current.onClick(event);
        });

        expect(preventDefault).not.toHaveBeenCalled();
        expect(useSelectionStore.getState().highlighted).toBeNull();
    });

    it("the arrows move the focus down and up the rows' links", () => {
        render(
            <table>
                <tbody>
                    <tr>
                        <td>
                            <a href="/samples/a">first</a>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <a href="/samples/b">second</a>
                        </td>
                    </tr>
                </tbody>
            </table>,
        );
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "a" }), { wrapper });
        const first = screen.getByText("first");
        const second = screen.getByText("second");

        act(() => {
            result.current.onKeyDown(fakeKeyEvent("ArrowDown", first));
        });
        expect(second).toHaveFocus();

        act(() => {
            result.current.onKeyDown(fakeKeyEvent("ArrowUp", second));
        });
        expect(first).toHaveFocus();
    });

    it("a double-click navigates to the entity's own route", async () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "module", hash: "def" }), { wrapper });
        const { event } = fakeMouseEvent();

        act(() => {
            result.current.onDoubleClick(event);
        });

        expect(await screen.findByText("module route")).toBeInTheDocument();
    });

    it("reflects the currently focused and highlighted entity", () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });

        act(() => {
            useSelectionStore.getState().focusSample("abc");
        });

        expect(result.current.isFocused).toBe(true);
        expect(result.current.isHighlighted).toBe(true);
    });
});
