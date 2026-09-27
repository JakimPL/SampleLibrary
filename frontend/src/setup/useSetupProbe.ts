import { useEffect, useState } from "react";

import { getSetupState, type SetupState } from "../api/setup";

/**
 * The setup routes' answer, asked once as the component mounts: the application's state where they
 * answer this browser, and null until they do. They answer only on the machine the application
 * runs on, and a server started as `sampleripper serve` alone has none, so null stays there.
 */
export function useSetupProbe(): SetupState | null {
    const [state, setState] = useState<SetupState | null>(null);

    useEffect(() => {
        let active = true;
        getSetupState()
            .then((found) => {
                if (active) {
                    setState(found);
                }
            })
            .catch(() => undefined);
        return (): void => {
            active = false;
        };
    }, []);

    return state;
}
