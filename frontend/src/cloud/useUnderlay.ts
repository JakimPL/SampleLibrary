import { type RefObject, useCallback, useEffect, useMemo, useRef } from "react";

import type { GridStyle } from "./cloudRenderSettings";
import { paintGrid } from "./gridPainter";
import { devicePixels } from "./markerGeometry";
import type { ViewTransform } from "./viewTransform";

/** The layer beneath the points as the cloud drives it. */
export interface Underlay {
    /** Paints the layer where `transform` puts the data, and keeps the transform for later repaints. */
    readonly draw: (transform: ViewTransform) => void;
}

/**
 * Keeps the canvas beneath the points on `canvasRef` painted: the grid, sized to whole device pixels
 * and repainted at the last transform whenever the theme's grid changes. The cloud calls `draw`
 * itself from the frame that draws a moved view, which keeps the grid locked to the points while
 * panning. A canvas without a 2D context, as under jsdom, stays blank.
 */
export function useUnderlay(canvasRef: RefObject<HTMLCanvasElement | null>, grid: GridStyle): Underlay {
    const transformRef = useRef<ViewTransform | null>(null);
    const gridRef = useRef(grid);
    gridRef.current = grid;

    const repaint = useCallback((): void => {
        const canvas = canvasRef.current;
        const transform = transformRef.current;
        const context = canvas?.getContext("2d") ?? null;
        if (canvas === null || transform === null || context === null) {
            return;
        }
        const width = devicePixels(transform.widthPx, transform.devicePixelRatio);
        const height = devicePixels(transform.heightPx, transform.devicePixelRatio);
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        context.clearRect(0, 0, width, height);
        paintGrid(context, transform, gridRef.current, { width, height });
    }, [canvasRef]);

    const draw = useCallback(
        (transform: ViewTransform): void => {
            transformRef.current = transform;
            repaint();
        },
        [repaint],
    );

    useEffect(() => {
        repaint();
    }, [grid, repaint]);

    return useMemo(() => ({ draw }), [draw]);
}
