import { act, render, renderHook, screen } from "@testing-library/react";
import type { KeyboardEvent, MouseEvent, ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useMorphStore } from "../../src/morph/morphStore";
import { OPENS_ENTITY_ATTRIBUTE } from "../../src/workspace/RowOpenLink";
import { INITIAL_SELECTION_STATE, useSelectionStore } from "../../src/workspace/selectionStore";
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

    it("a modified click is left alone, neither highlighting nor preventing the default navigation", () => {
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
        const { event, preventDefault } = fakeMouseEvent({ ctrlKey: true });

        act(() => {
            result.current.onClick(event);
        });

        expect(preventDefault).not.toHaveBeenCalled();
        expect(useSelectionStore.getState().highlighted).toBeNull();
    });

    it("a Shift-click on a sample joins it to the sample in hand and prevents the default navigation", () => {
        useSelectionStore.getState().focusSample("anchor");
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
        const { event, preventDefault } = fakeMouseEvent({ shiftKey: true });

        act(() => {
            result.current.onClick(event);
        });

        expect(preventDefault).toHaveBeenCalled();
        expect(useMorphStore.getState()).toMatchObject({ first: "anchor", second: "abc" });
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "anchor" });
    });

    it("a Shift-click with nothing in hand opens a pair on the clicked sample", () => {
        useSelectionStore.setState(INITIAL_SELECTION_STATE);
        useMorphStore.getState().clear();
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
        const { event } = fakeMouseEvent({ shiftKey: true });

        act(() => {
            result.current.onClick(event);
        });

        expect(useMorphStore.getState()).toMatchObject({ first: "abc", second: null });
    });

    it("a Shift-click on a module does nothing, since a module has no pair to join", () => {
        useMorphStore.getState().clear();
        const { result } = renderHook(() => useEntityRowInteractions({ kind: "module", hash: "def" }), { wrapper });
        const { event, preventDefault } = fakeMouseEvent({ shiftKey: true });

        act(() => {
            result.current.onClick(event);
        });

        expect(preventDefault).not.toHaveBeenCalled();
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null });
    });

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
        control.setAttribute(OPENS_ENTITY_ATTRIBUTE, "");
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

    it("M joins a sample to the one in hand, and does nothing for a module", () => {
        useSelectionStore.getState().focusSample("anchor");
        const sample = renderHook(() => useEntityRowInteractions({ kind: "sample", hash: "abc" }), { wrapper });
        const module = renderHook(() => useEntityRowInteractions({ kind: "module", hash: "def" }), { wrapper });
        const element = document.createElement("a");

        act(() => {
            module.result.current.onKeyDown(fakeKeyEvent("m", element));
        });
        expect(useMorphStore.getState()).toMatchObject({ first: null, second: null });

        act(() => {
            sample.result.current.onKeyDown(fakeKeyEvent("m", element));
        });
        expect(useMorphStore.getState()).toMatchObject({ first: "anchor", second: "abc" });
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
