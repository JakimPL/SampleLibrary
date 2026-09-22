import { createBrowserRouter, type RouteObject } from "react-router-dom";

import { AppShell } from "../shell/AppShell";
import { PANEL_REGISTRY } from "../workspace/panelRegistry";
import { NotFoundView } from "./NotFoundView";
import { RouteErrorView } from "./RouteErrorView";
import type { RouteView } from "./shellView";

const SAMPLE_ROUTE_VIEW: RouteView = { kind: "sample" };
const MODULE_ROUTE_VIEW: RouteView = { kind: "module" };

/** One address per panel that has one, each rendering the same shell so a change of address keeps it mounted. */
function panelRoutes(): RouteObject[] {
    return Object.values(PANEL_REGISTRY).flatMap((definition) =>
        definition.path === null
            ? []
            : [{ path: definition.path, element: <AppShell routeView={{ kind: "panel", panelId: definition.id }} /> }],
    );
}

/**
 * Every address the application answers: a panel's own, a sample's, a module's, and a plain page
 * for anything else, all under one error element so a render that throws leaves a page stating
 * what broke rather than a blank document.
 */
export const routes: RouteObject[] = [
    {
        errorElement: <RouteErrorView />,
        children: [
            ...panelRoutes(),
            { path: "/samples/:sampleHash", element: <AppShell routeView={SAMPLE_ROUTE_VIEW} /> },
            { path: "/modules/:moduleHash", element: <AppShell routeView={MODULE_ROUTE_VIEW} /> },
            { path: "*", element: <NotFoundView /> },
        ],
    },
];

export const router = createBrowserRouter(routes);
