import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiError } from "../../src/api/client";
import { requestJson } from "../../src/api/client";

describe("requestJson", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("returns the parsed JSON body on a successful response", async () => {
        const payload = { greeting: "hello" };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) }));

        const result = await requestJson<typeof payload>("/greeting");

        expect(result).toEqual(payload);
    });

    it("throws an ApiError carrying the status on a non-ok response", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

        await expect(requestJson("/missing")).rejects.toMatchObject({ status: 404 } satisfies Partial<ApiError>);
    });
});
