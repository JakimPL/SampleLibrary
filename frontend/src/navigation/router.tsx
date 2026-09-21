import { createBrowserRouter, type RouteObject } from "react-router-dom";

import { WorkspaceShell } from "../workspace/WorkspaceShell";
import { NotFoundView } from "./NotFoundView";
import { RouteErrorView } from "./RouteErrorView";

/**
 * Every address the application answers: the workspace at its three views, and a plain page for
 * anything else, all under one error element so a render that throws leaves a page stating what
 * broke rather than a blank document.
 */
export const routes: RouteObject[] = [
    {
        errorElement: <RouteErrorView />,
        children: [
            { path: "/", element: <WorkspaceShell /> },
            { path: "/modules/:moduleHash", element: <WorkspaceShell /> },
            { path: "/samples/:sampleHash", element: <WorkspaceShell /> },
            { path: "*", element: <NotFoundView /> },
        ],
    },
];

export const router = createBrowserRouter(routes);
