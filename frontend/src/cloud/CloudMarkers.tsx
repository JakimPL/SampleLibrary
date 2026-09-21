import type { ReactElement } from "react";

import type { ScreenPoint } from "./linkGeometry";
import type { MarkerAppearance } from "./markerGeometry";
import { PointMarker } from "./PointMarker";

/** Where the markers over the cloud stand: the selected point and the hovered one, each null while there is none. */
export interface MarkerPositions {
    readonly selected: ScreenPoint | null;
    readonly hovered: ScreenPoint | null;
}

export const NO_MARKERS: MarkerPositions = { selected: null, hovered: null };

function samePoint(first: ScreenPoint | null, second: ScreenPoint | null): boolean {
    return first === null || second === null ? first === second : first[0] === second[0] && first[1] === second[1];
}

export function sameMarkers(first: MarkerPositions, second: MarkerPositions): boolean {
    return samePoint(first.selected, second.selected) && samePoint(first.hovered, second.hovered);
}

interface CloudMarkersProps {
    readonly positions: MarkerPositions;
    readonly appearance: MarkerAppearance;
}

/**
 * The selected and the hovered point's markers, the hovered one on top. It is a cue alone, so every
 * pointer passes through it to the points beneath.
 */
export function CloudMarkers({ positions, appearance }: CloudMarkersProps): ReactElement {
    return (
        <svg className="cloud-markers" aria-hidden>
            {positions.selected !== null && (
                <PointMarker
                    className="cloud-marker-selected"
                    center={positions.selected}
                    appearance={appearance}
                    filled={false}
                />
            )}
            {positions.hovered !== null && (
                <PointMarker
                    className="cloud-marker-hover"
                    center={positions.hovered}
                    appearance={appearance}
                    filled={false}
                />
            )}
        </svg>
    );
}
