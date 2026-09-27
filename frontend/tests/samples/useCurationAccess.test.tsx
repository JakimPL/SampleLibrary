import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as CurationApi from "../../src/api/curation";
import type * as CurationAccess from "../../src/samples/useCurationAccess";

const { getCurationAccess } = vi.hoisted(() => ({ getCurationAccess: vi.fn() }));

vi.mock("../../src/api/curation", async () => {
    const actual = await vi.importActual<typeof CurationApi>("../../src/api/curation");
    return { ...actual, getCurationAccess };
});

async function actualHook(): Promise<typeof CurationAccess.useCurationAccess> {
    const actual = await vi.importActual<typeof CurationAccess>("../../src/samples/useCurationAccess");
    return actual.useCurationAccess;
}

describe("useCurationAccess", () => {
    it("shows and offers the labels once the server says the person here may change them", async () => {
        getCurationAccess.mockResolvedValue({ label_editing: true, curation_shown: true });
        const useCurationAccess = await actualHook();
        const { result } = renderHook(() => useCurationAccess());

        expect(result.current).toEqual({ curationShown: false, labelEditing: false });
        await waitFor(() => {
            expect(result.current).toEqual({ curationShown: true, labelEditing: true });
        });
    });

    it("shows the labels without editing where the server says they may only be seen", async () => {
        getCurationAccess.mockResolvedValue({ label_editing: false, curation_shown: true });
        const useCurationAccess = await actualHook();
        const { result } = renderHook(() => useCurationAccess());

        await waitFor(() => {
            expect(result.current).toEqual({ curationShown: true, labelEditing: false });
        });
    });

    it("shows nothing of the labels where the server shows none", async () => {
        getCurationAccess.mockResolvedValue({ label_editing: false, curation_shown: false });
        const useCurationAccess = await actualHook();
        const { result } = renderHook(() => useCurationAccess());

        await waitFor(() => {
            expect(getCurationAccess).toHaveBeenCalled();
        });
        expect(result.current).toEqual({ curationShown: false, labelEditing: false });
    });

    it("shows and offers nothing where the server cannot say", async () => {
        getCurationAccess.mockRejectedValue(new Error("no answer"));
        const useCurationAccess = await actualHook();
        const { result } = renderHook(() => useCurationAccess());

        await waitFor(() => {
            expect(getCurationAccess).toHaveBeenCalled();
        });
        expect(result.current).toEqual({ curationShown: false, labelEditing: false });
    });
});
