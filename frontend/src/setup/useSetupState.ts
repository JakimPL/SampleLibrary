import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { getSetupState, type SetupState } from "../api/setup";
import { describeError } from "../shared/fetchState";

/** How often the page asks again while the library opens or a build runs, and while it waits otherwise. */
const BUSY_POLL_MS = 1000;
const IDLE_POLL_MS = 5000;
const MISSING_STATUS = 404;

export type SetupSource =
    | { readonly status: "loading" }
    | { readonly status: "absent" }
    | { readonly status: "error"; readonly message: string }
    | { readonly status: "ready"; readonly state: SetupState };

export interface SetupStateHandle {
    readonly source: SetupSource;
    /** Takes a state a write answered with, so the page shows it before the next poll. */
    readonly accept: (state: SetupState) => void;
}

function isBusy(state: SetupState): boolean {
    return state.status === "starting" || state.build?.status === "running";
}

/**
 * The application's setup state, asked again every second while the library opens or a build runs
 * and every few seconds otherwise. A server without setup routes — `samplelibrary serve` alone —
 * reports them absent, and the page then says setup belongs to the application.
 */
export function useSetupState(): SetupStateHandle {
    const [source, setSource] = useState<SetupSource>({ status: "loading" });

    const accept = useCallback((state: SetupState) => {
        setSource({ status: "ready", state });
    }, []);

    useEffect(() => {
        let active = true;
        let timer: number | undefined;
        function schedule(delay: number): void {
            timer = window.setTimeout(() => {
                void poll();
            }, delay);
        }
        async function poll(): Promise<void> {
            try {
                const state = await getSetupState();
                if (!active) {
                    return;
                }
                setSource({ status: "ready", state });
                schedule(isBusy(state) ? BUSY_POLL_MS : IDLE_POLL_MS);
            } catch (error: unknown) {
                if (!active) {
                    return;
                }
                if (error instanceof ApiError && error.status === MISSING_STATUS) {
                    setSource({ status: "absent" });
                    return;
                }
                setSource({ status: "error", message: describeError(error) });
                schedule(IDLE_POLL_MS);
            }
        }
        void poll();
        return (): void => {
            active = false;
            window.clearTimeout(timer);
        };
    }, []);

    return { source, accept };
}
