import { describe, expect, it, vi } from "vitest";

import { cameraOf, panBy, zoomAbout } from "../../../src/cloud/touch/cameraControl";

const VIEWPORT = { widthPx: 600, heightPx: 300, devicePixelRatio: 1 };

function fakeCamera(): { readonly pan: ReturnType<typeof vi.fn>; readonly scale: ReturnType<typeof vi.fn> } {
    return { pan: vi.fn(), scale: vi.fn() };
}

describe("cameraOf", () => {
    it("takes an object with pan and scale, and nothing else", () => {
        const camera = fakeCamera();

        expect(cameraOf(camera)).toBe(camera);
        expect(cameraOf({ pan: vi.fn() })).toBeNull();
        expect(cameraOf(null)).toBeNull();
        expect(cameraOf("camera")).toBeNull();
    });
});

describe("panBy", () => {
    it("carries the points with the finger, half the height being one unit and the vertical axis flipped", () => {
        const camera = fakeCamera();

        panBy(camera, VIEWPORT, 30, 15);

        expect(camera.pan).toHaveBeenCalledWith([0.2, -0.1]);
    });
});

describe("zoomAbout", () => {
    it("scales about the finger's place in the camera's space, the horizontal axis stretched by the aspect", () => {
        const camera = fakeCamera();

        zoomAbout(camera, VIEWPORT, 2, 450, 75);

        expect(camera.scale).toHaveBeenCalledWith([2, 2], [1, 0.5]);
    });

    it("names the middle of the surface as the origin", () => {
        const camera = fakeCamera();

        zoomAbout(camera, VIEWPORT, 0.5, 300, 150);

        expect(camera.scale).toHaveBeenCalledWith([0.5, 0.5], [0, 0]);
    });
});
