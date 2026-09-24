import { type ReactElement, useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { getSetupState } from "../api/setup";

export const SETUP_PATH = "/setup";

/**
 * Sends a person to the setup page while the application has no library to show, and renders the
 * workspace otherwise. A server without setup routes, or one that fails to answer, shows the
 * workspace as it always has.
 */
export function SetupGate(): ReactElement {
    const [unconfigured, setUnconfigured] = useState(false);

    useEffect(() => {
        let active = true;
        getSetupState()
            .then((state) => {
                if (active && state.sources === null) {
                    setUnconfigured(true);
                }
            })
            .catch(() => undefined);
        return (): void => {
            active = false;
        };
    }, []);

    return unconfigured ? <Navigate to={SETUP_PATH} replace /> : <Outlet />;
}
