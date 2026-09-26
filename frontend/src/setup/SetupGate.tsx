import type { ReactElement } from "react";
import { Navigate, Outlet } from "react-router-dom";

import { useSetupProbe } from "./useSetupProbe";

export const SETUP_PATH = "/setup";

/**
 * Sends a person to the setup page while the application has no library to show, and renders the
 * workspace otherwise. A server without setup routes, or one that fails to answer, shows the
 * workspace as it always has.
 */
export function SetupGate(): ReactElement {
    const setup = useSetupProbe();
    return setup?.sources === null ? <Navigate to={SETUP_PATH} replace /> : <Outlet />;
}
