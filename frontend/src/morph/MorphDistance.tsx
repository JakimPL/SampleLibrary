import type { ReactElement } from "react";
import { useCallback } from "react";

import { getSampleDistance } from "../api/samples";
import { useFetch } from "../shared/useFetch";

const DISTANCE_DECIMAL_PLACES = 3;

interface MorphDistanceProps {
    readonly first: string;
    readonly second: string;
}

/**
 * How far apart the two ends of the pair sit, as their persisted spectral vectors measure it.
 *
 * It reads the pair the panel already holds rather than a selection of its own, so the number under
 * the slider always belongs to the morph the slider runs along, and it says how far a listener is
 * traveling before they hear it.
 */
export function MorphDistance({ first, second }: MorphDistanceProps): ReactElement {
    const loader = useCallback(() => getSampleDistance(first, second), [first, second]);
    const state = useFetch(loader, [first, second]);

    return (
        <p className="morph-distance">
            {state.status === "loading" && <span className="cell-muted">Computing distance…</span>}
            {state.status === "error" && <span className="error-notice">{state.message}</span>}
            {state.status === "success" && (
                <span className="mono">distance {state.data.distance.toFixed(DISTANCE_DECIMAL_PLACES)}</span>
            )}
        </p>
    );
}
