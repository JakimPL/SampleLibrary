import { act, renderHook, screen } from "@testing-library/react";
import type { MouseEvent, ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

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

function fakeMouseEvent(overrides: Partial<Record<"button" | "ctrlKey", number | boolean>> = {}): FakeMouseEvent {
    const preventDefault = vi.fn();
    const event = {
        button: 0,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        altKey: false,
        preventDefault,
        ...overrides,
    } as unknown as MouseEvent;
    return { event, preventDefault };
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
