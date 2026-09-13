import { useCallback, useState } from "react";

import { getMorphStatus, type MorphAvailability } from "../api/morph";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

export interface MorphStatus {
    readonly state: FetchState<MorphAvailability>;
    readonly available: boolean;
    readonly refresh: () => void;
}

/**
 * Whether morphs can be rendered right now. Asked once when the panel mounts and again on request,
 * since the inference process may be started after the app is open; a request that fails reads
 * as the process being away, which is what a listener needs to know either way.
 */
export function useMorphStatus(): MorphStatus {
    const [attempt, setAttempt] = useState(0);
    const state = useFetch(getMorphStatus, [attempt]);
    const refresh = useCallback(() => {
        setAttempt((current) => current + 1);
    }, []);

    return { state, available: state.status === "success" && state.data.available, refresh };
}
