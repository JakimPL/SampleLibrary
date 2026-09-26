import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type * as LabelEditing from "../../src/samples/useLabelEditing";

const { getLabelEditing } = vi.hoisted(() => ({ getLabelEditing: vi.fn() }));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, getLabelEditing };
});

async function actualHook(): Promise<typeof LabelEditing.useLabelEditing> {
    const actual = await vi.importActual<typeof LabelEditing>("../../src/samples/useLabelEditing");
    return actual.useLabelEditing;
}

describe("useLabelEditing", () => {
    it("offers editing once the server says the person here may change labels", async () => {
        getLabelEditing.mockResolvedValue({ label_editing: true });
        const useLabelEditing = await actualHook();
        const { result } = renderHook(() => useLabelEditing());

        expect(result.current).toBe(false);
        await waitFor(() => {
            expect(result.current).toBe(true);
        });
    });

    it("keeps editing off where the server says labels may only be seen", async () => {
        getLabelEditing.mockResolvedValue({ label_editing: false });
        const useLabelEditing = await actualHook();
        const { result } = renderHook(() => useLabelEditing());

        await waitFor(() => {
            expect(getLabelEditing).toHaveBeenCalled();
        });
        expect(result.current).toBe(false);
    });

    it("keeps editing off where the server cannot say", async () => {
        getLabelEditing.mockRejectedValue(new Error("no answer"));
        const useLabelEditing = await actualHook();
        const { result } = renderHook(() => useLabelEditing());

        await waitFor(() => {
            expect(getLabelEditing).toHaveBeenCalled();
        });
        expect(result.current).toBe(false);
    });
});
