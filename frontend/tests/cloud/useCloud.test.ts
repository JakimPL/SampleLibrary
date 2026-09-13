import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../src/api/cloud";
import { useCloud } from "../../src/cloud/useCloud";
import { useModuleCloud } from "../../src/cloud/useModuleCloud";

const { getCloud, getModuleCloud } = vi.hoisted(() => ({
    getCloud: vi.fn().mockReturnValue(new Promise(() => undefined)),
    getModuleCloud: vi.fn().mockReturnValue(new Promise(() => undefined)),
}));

vi.mock("../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../src/api/cloud");
    return { ...actual, getCloud, getModuleCloud };
});

describe("the cloud's points", () => {
    it("are requested once however many panels mount them", () => {
        renderHook(() => useCloud());
        renderHook(() => useCloud());
        renderHook(() => useModuleCloud());
        renderHook(() => useModuleCloud());

        expect(getCloud).toHaveBeenCalledTimes(1);
        expect(getModuleCloud).toHaveBeenCalledTimes(1);
    });
});
