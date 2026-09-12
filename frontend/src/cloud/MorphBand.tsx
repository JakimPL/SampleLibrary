import type { ReactElement } from "react";

import type { ScreenPoint } from "./linkGeometry";

const ANCHOR_RADIUS_PX = 6;

interface MorphBandProps {
    readonly anchor: ScreenPoint;
    readonly cursor: ScreenPoint;
}

/**
 * The pair a Shift-click would join, shown before it lands: a dotted line from the sample that
 * anchors the next morph to where the cursor stands, with a ring on the anchor. It is a cue alone,
 * so every pointer passes through it to the points beneath.
 */
export function MorphBand({ anchor, cursor }: MorphBandProps): ReactElement {
    return (
        <svg className="morph-band" aria-hidden>
            <line className="morph-band-line" x1={anchor[0]} y1={anchor[1]} x2={cursor[0]} y2={cursor[1]} />
            <circle className="morph-band-anchor" cx={anchor[0]} cy={anchor[1]} r={ANCHOR_RADIUS_PX} />
        </svg>
    );
}
