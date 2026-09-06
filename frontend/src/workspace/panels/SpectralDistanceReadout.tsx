import type { ReactElement } from "react";
import { useCallback } from "react";

import { getSampleDistance } from "../../api/samples";
import { shortHash } from "../../shared/format";
import { useFetch } from "../../shared/useFetch";
import { useSelectionStore } from "../selectionStore";

const DISTANCE_DECIMAL_PLACES = 3;

interface ActiveComparisonProps {
    readonly focusedSampleHash: string;
    readonly comparisonSampleHash: string;
    readonly onClear: () => void;
}

function ActiveComparison({ focusedSampleHash, comparisonSampleHash, onClear }: ActiveComparisonProps): ReactElement {
    const loader = useCallback(
        () => getSampleDistance(focusedSampleHash, comparisonSampleHash),
        [focusedSampleHash, comparisonSampleHash],
    );
    const state = useFetch(loader, [focusedSampleHash, comparisonSampleHash]);

    return (
        <div className="spectral-distance-readout">
            <span className="mono">
                {shortHash(focusedSampleHash)} ↔ {shortHash(comparisonSampleHash)}
            </span>
            {state.status === "loading" && <span className="cell-muted">Computing distance…</span>}
            {state.status === "error" && <span className="error-notice">{state.message}</span>}
            {state.status === "success" && (
                <span className="mono">distance {state.data.distance.toFixed(DISTANCE_DECIMAL_PLACES)}</span>
            )}
            <button type="button" onClick={onClear}>
                Clear comparison
            </button>
        </div>
    );
}

/**
 * A compact spectral-distance readout between the focused sample and a second, Shift-clicked
 * comparison sample. Renders nothing until both are set, and nothing at all replaces it once one
 * is cleared -- comparing stays a deliberate, two-sample-at-a-time act rather than a persisted
 * history or a batch operation.
 */
export function SpectralDistanceReadout(): ReactElement | null {
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);
    const comparisonSampleHash = useSelectionStore((state) => state.comparisonSampleHash);
    const clearComparisonSample = useSelectionStore((state) => state.clearComparisonSample);

    if (focusedSampleHash === null || comparisonSampleHash === null) {
        return null;
    }

    return (
        <ActiveComparison
            focusedSampleHash={focusedSampleHash}
            comparisonSampleHash={comparisonSampleHash}
            onClear={clearComparisonSample}
        />
    );
}
