import type { ReactElement } from "react";

import type { ScreenPoint } from "./linkGeometry";

const ORIGIN_RADIUS_PX = 6;

interface MorphBandProps {
    readonly origin: ScreenPoint;
    readonly cursor: ScreenPoint;
}

/**
 * The pair a release would join, shown while the right button is held: a dotted line from the
 * point the drag started at to where the cursor stands, with a ring on that origin. It is a cue
 * alone, so every pointer passes through it to the points beneath.
 */
export function MorphBand({ origin, cursor }: MorphBandProps): ReactElement {
    return (
        <svg className="morph-band" aria-hidden>
            <line className="morph-band-line" x1={origin[0]} y1={origin[1]} x2={cursor[0]} y2={cursor[1]} />
            <circle className="morph-band-origin" cx={origin[0]} cy={origin[1]} r={ORIGIN_RADIUS_PX} />
        </svg>
    );
}
