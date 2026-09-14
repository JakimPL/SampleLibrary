import type { ReactElement } from "react";

import type { ScreenPoint } from "./linkGeometry";
import { lineBetweenMarkers, type MarkerAppearance } from "./markerGeometry";
import { PointMarker } from "./PointMarker";

interface MorphBandProps {
    readonly origin: ScreenPoint;
    readonly cursor: ScreenPoint;
    /** Whether the far end has snapped to a point, whose hover marker the line then stops short of. */
    readonly endsOnPoint: boolean;
    readonly appearance: MarkerAppearance;
}

/**
 * The pair a release would join, shown while the right button is held: a dotted line from the
 * point the drag started at to where the cursor stands, with the origin marked in the theme's point
 * shape and the line meeting each marker at its edge. It is a cue alone, so every pointer passes
 * through it to the points beneath.
 */
export function MorphBand({ origin, cursor, endsOnPoint, appearance }: MorphBandProps): ReactElement {
    const line = lineBetweenMarkers(origin, cursor, appearance, endsOnPoint);
    return (
        <svg className="morph-band" aria-hidden>
            {line !== null && (
                <line className="morph-band-line" x1={line[0][0]} y1={line[0][1]} x2={line[1][0]} y2={line[1][1]} />
            )}
            <PointMarker className="morph-band-origin" center={origin} appearance={appearance} filled={false} />
        </svg>
    );
}
