import type { KeyboardEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { playOnSpace } from "../../src/samples/playKey";

function keyEvent(key: string): {
    readonly event: KeyboardEvent<HTMLElement>;
    readonly preventDefault: ReturnType<typeof vi.fn>;
} {
    const preventDefault = vi.fn();
    return { event: { key, preventDefault } as unknown as KeyboardEvent<HTMLElement>, preventDefault };
}

const SOURCE = { key: "abc", url: "/api/samples/abc/audio", playbackRateHz: null };

describe("playOnSpace", () => {
    it("plays on the space bar and keeps the page from scrolling", () => {
        const play = vi.fn();
        const { event, preventDefault } = keyEvent(" ");

        expect(playOnSpace(event, SOURCE, play)).toBe(true);
        expect(play).toHaveBeenCalledWith(SOURCE);
        expect(preventDefault).toHaveBeenCalled();
    });

    it("leaves any other key alone", () => {
        const play = vi.fn();
        const { event, preventDefault } = keyEvent("Enter");

        expect(playOnSpace(event, SOURCE, play)).toBe(false);
        expect(play).not.toHaveBeenCalled();
        expect(preventDefault).not.toHaveBeenCalled();
    });
});
