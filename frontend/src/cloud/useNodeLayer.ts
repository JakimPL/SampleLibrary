import { type RefObject, useCallback, useEffect, useMemo, useRef } from "react";

import { createHollowPointRenderer, type HollowPointRenderer, type NodeFrameStyle } from "./hollowPointRenderer";
import type { NodeGeometry } from "./nodeGeometry";
import type { ViewTransform } from "./viewTransform";

/** The node layer as the cloud drives it. */
export interface NodeLayer {
    /** Draws every node where `transform` puts it, and keeps the transform for later redraws. */
    readonly draw: (transform: ViewTransform) => void;
}

/**
 * Keeps the node layer on `canvasRef` in step with the cloud: the renderer lives as long as the
 * canvas, takes new geometry and a new palette when they change, and redraws at the last
 * transform it drew so a new coloring or theme shows at once. The cloud calls `draw` itself from
 * the frame that draws a moved view, which keeps the markers on the points while panning.
 */
export function useNodeLayer(
    canvasRef: RefObject<HTMLCanvasElement | null>,
    geometry: NodeGeometry,
    palette: Uint8Array,
    style: NodeFrameStyle,
): NodeLayer {
    const rendererRef = useRef<HollowPointRenderer | null>(null);
    const transformRef = useRef<ViewTransform | null>(null);
    const styleRef = useRef(style);
    styleRef.current = style;

    const redraw = useCallback((): void => {
        const renderer = rendererRef.current;
        const transform = transformRef.current;
        if (renderer !== null && transform !== null) {
            renderer.draw(transform, styleRef.current);
        }
    }, []);

    const draw = useCallback(
        (transform: ViewTransform): void => {
            transformRef.current = transform;
            redraw();
        },
        [redraw],
    );

    useEffect(() => {
        const canvas = canvasRef.current;
        if (canvas === null) {
            return undefined;
        }
        const renderer = createHollowPointRenderer(canvas);
        rendererRef.current = renderer;
        return (): void => {
            renderer?.destroy();
            rendererRef.current = null;
        };
    }, [canvasRef]);

    useEffect(() => {
        rendererRef.current?.setGeometry(geometry);
        redraw();
    }, [geometry, redraw]);

    useEffect(() => {
        rendererRef.current?.setPalette(palette);
        redraw();
    }, [palette, redraw]);

    useEffect(() => {
        redraw();
    }, [style, redraw]);

    return useMemo(() => ({ draw }), [draw]);
}
