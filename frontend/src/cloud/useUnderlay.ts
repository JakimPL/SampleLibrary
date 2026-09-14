import { type RefObject, useCallback, useEffect, useMemo, useRef } from "react";

import type { GridStyle } from "./cloudRenderSettings";
import { type GlowImage, paintGlow } from "./densityGlow";
import { paintGrid } from "./gridPainter";
import { devicePixels } from "./markerGeometry";
import type { ViewTransform } from "./viewTransform";

/** The layer beneath the points as the cloud drives it. */
export interface Underlay {
    /** Paints the layer where `transform` puts the data, and keeps the transform for later repaints. */
    readonly draw: (transform: ViewTransform) => void;
}

/**
 * Keeps the canvas beneath the points on `canvasRef` painted: the grid first, then the density glow
 * over it where the theme has one, both sized to whole device pixels and repainted at the last
 * transform whenever the grid or the glow changes. The cloud calls `draw` itself from the frame that
 * draws a moved view, which keeps the layer locked to the points while panning. A canvas without a
 * 2D context, as under jsdom, stays blank.
 */
export function useUnderlay(
    canvasRef: RefObject<HTMLCanvasElement | null>,
    grid: GridStyle,
    glow: GlowImage | null,
): Underlay {
    const transformRef = useRef<ViewTransform | null>(null);
    const gridRef = useRef(grid);
    gridRef.current = grid;
    const glowRef = useRef(glow);
    glowRef.current = glow;

    const repaint = useCallback((): void => {
        const canvas = canvasRef.current;
        const transform = transformRef.current;
        const context = canvas?.getContext("2d") ?? null;
        if (canvas === null || transform === null || context === null) {
            return;
        }
        const size = {
            width: devicePixels(transform.widthPx, transform.devicePixelRatio),
            height: devicePixels(transform.heightPx, transform.devicePixelRatio),
        };
        if (canvas.width !== size.width || canvas.height !== size.height) {
            canvas.width = size.width;
            canvas.height = size.height;
        }
        context.clearRect(0, 0, size.width, size.height);
        paintGrid(context, transform, gridRef.current, size);
        const currentGlow = glowRef.current;
        if (currentGlow !== null) {
            paintGlow(context, transform, currentGlow, size);
        }
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
    }, [grid, glow, repaint]);

    return useMemo(() => ({ draw }), [draw]);
}
