import { render } from "@testing-library/react";
import { type ReactElement, useRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NodeFrameStyle } from "../../src/cloud/hollowPointRenderer";
import type { NodeGeometry } from "../../src/cloud/nodeGeometry";
import { type NodeLayer, useNodeLayer } from "../../src/cloud/useNodeLayer";
import { viewTransformOf } from "../../src/cloud/viewTransform";

const { renderer, createRendererMock } = vi.hoisted(() => {
    const renderer = { setGeometry: vi.fn(), setPalette: vi.fn(), draw: vi.fn(), clear: vi.fn(), destroy: vi.fn() };
    return { renderer, createRendererMock: vi.fn(() => renderer) };
});

vi.mock("../../src/cloud/hollowPointRenderer", () => ({ createHollowPointRenderer: createRendererMock }));

const GEOMETRY: NodeGeometry = { positions: new Float32Array([0, 0]), slots: new Float32Array([0]), count: 1 };
const PALETTE = new Uint8Array([255, 255, 255, 255]);
const STYLE: NodeFrameStyle = { shape: "square", sizePx: 7, lineWidthPx: 1, fillOpacity: 0 };
const TRANSFORM = viewTransformOf(new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]), {
    widthPx: 600,
    heightPx: 400,
    devicePixelRatio: 1.75,
});

interface HarnessProps {
    readonly geometry: NodeGeometry;
    readonly palette: Uint8Array;
    readonly style: NodeFrameStyle;
    readonly onLayer: (layer: NodeLayer) => void;
}

function Harness({ geometry, palette, style, onLayer }: HarnessProps): ReactElement {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    onLayer(useNodeLayer(canvasRef, geometry, palette, style));
    return <canvas ref={canvasRef} />;
}

beforeEach(() => {
    createRendererMock.mockClear();
    for (const method of Object.values(renderer)) {
        method.mockClear();
    }
});

interface CapturedLayer {
    layer: NodeLayer | null;
}

describe("useNodeLayer", () => {
    it("hands the renderer its geometry and palette, and draws once it is given a transform", () => {
        const captured: CapturedLayer = { layer: null };
        render(
            <Harness
                geometry={GEOMETRY}
                palette={PALETTE}
                style={STYLE}
                onLayer={(next) => {
                    captured.layer = next;
                }}
            />,
        );

        expect(renderer.setGeometry).toHaveBeenCalledWith(GEOMETRY);
        expect(renderer.setPalette).toHaveBeenCalledWith(PALETTE);
        expect(renderer.draw).not.toHaveBeenCalled();

        captured.layer?.draw(TRANSFORM);

        expect(renderer.draw).toHaveBeenLastCalledWith(TRANSFORM, STYLE);
    });

    it("redraws at the last transform when the palette or the style changes", () => {
        const captured: CapturedLayer = { layer: null };
        const onLayer = (next: NodeLayer): void => {
            captured.layer = next;
        };
        const { rerender } = render(<Harness geometry={GEOMETRY} palette={PALETTE} style={STYLE} onLayer={onLayer} />);
        captured.layer?.draw(TRANSFORM);
        renderer.draw.mockClear();

        const nextPalette = new Uint8Array([0, 0, 255, 255]);
        const nextStyle: NodeFrameStyle = { ...STYLE, shape: "circle" };
        rerender(<Harness geometry={GEOMETRY} palette={nextPalette} style={nextStyle} onLayer={onLayer} />);

        expect(renderer.setPalette).toHaveBeenLastCalledWith(nextPalette);
        expect(renderer.draw).toHaveBeenLastCalledWith(TRANSFORM, nextStyle);
    });

    it("destroys the renderer with the canvas", () => {
        const { unmount } = render(<Harness geometry={GEOMETRY} palette={PALETTE} style={STYLE} onLayer={vi.fn()} />);

        unmount();

        expect(renderer.destroy).toHaveBeenCalledTimes(1);
    });
});
