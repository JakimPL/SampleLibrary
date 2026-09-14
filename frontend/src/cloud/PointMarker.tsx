import type { ReactElement } from "react";

import { classNames } from "../shared/classNames";
import type { ScreenPoint } from "./linkGeometry";
import { crispSquare, type MarkerAppearance, ringFrame } from "./markerGeometry";

const SQUARE_SHAPE = "square";
const SIDES_OF_A_STROKE = 2;

interface PointMarkerProps {
    readonly center: ScreenPoint;
    readonly appearance: MarkerAppearance;
    /** What the marker marks, which the stylesheet colors it by. */
    readonly className: string;
    /** Paints the marker's inside as well as its edge. */
    readonly filled: boolean;
}

/**
 * One marker over a cloud point, drawn in the theme's point shape: a ring for round points, and a
 * square framed on whole device pixels for square ones. A casing -- a wider stroke in the
 * background color beneath the marker's own -- keeps a ring legible over a dense patch of points.
 * Colors come from the stylesheet through `className`.
 */
export function PointMarker({ center, appearance, className, filled }: PointMarkerProps): ReactElement {
    const bodyClass = classNames("cloud-marker-stroke", filled && "cloud-marker-filled");
    const casingWidth = appearance.casingWidthPx * SIDES_OF_A_STROKE;
    if (appearance.shape === SQUARE_SHAPE) {
        const frame = crispSquare(center, appearance.sizePx, appearance.lineWidthPx, appearance.devicePixelRatio);
        return (
            <g className={className}>
                {casingWidth > 0 && (
                    <rect
                        className="cloud-marker-casing"
                        x={frame.x}
                        y={frame.y}
                        width={frame.side}
                        height={frame.side}
                        strokeWidth={frame.strokeWidth + casingWidth}
                    />
                )}
                <rect
                    className={bodyClass}
                    x={frame.x}
                    y={frame.y}
                    width={frame.side}
                    height={frame.side}
                    strokeWidth={frame.strokeWidth}
                    shapeRendering="crispEdges"
                />
            </g>
        );
    }
    const ring = ringFrame(appearance.sizePx, appearance.lineWidthPx);
    return (
        <g className={className}>
            {casingWidth > 0 && (
                <circle
                    className="cloud-marker-casing"
                    cx={center[0]}
                    cy={center[1]}
                    r={ring.radius}
                    strokeWidth={ring.strokeWidth + casingWidth}
                />
            )}
            <circle
                className={bodyClass}
                cx={center[0]}
                cy={center[1]}
                r={ring.radius}
                strokeWidth={ring.strokeWidth}
            />
        </g>
    );
}
