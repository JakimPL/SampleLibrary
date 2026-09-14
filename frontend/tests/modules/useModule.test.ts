import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as ModulesApi from "../../src/api/modules";
import { useModule } from "../../src/modules/useModule";

const { getModule } = vi.hoisted(() => ({ getModule: vi.fn() }));

vi.mock("../../src/api/modules", async () => {
    const actual = await vi.importActual<typeof ModulesApi>("../../src/api/modules");
    return { ...actual, getModule };
});

describe("useModule", () => {
    it("asks once for a module that a hover and a panel both show", async () => {
        getModule.mockResolvedValue({ hash: "m", title: "a song", occurrences: [] });

        const hover = renderHook(() => useModule("m"));
        const panel = renderHook(() => useModule("m"));

        await waitFor(() => {
            expect(hover.result.current.status).toBe("success");
            expect(panel.result.current.status).toBe("success");
        });
        expect(getModule).toHaveBeenCalledTimes(1);
    });
});
