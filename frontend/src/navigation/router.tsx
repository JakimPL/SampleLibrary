import { createBrowserRouter, type RouteObject } from "react-router-dom";

import { WorkspaceShell } from "../workspace/WorkspaceShell";
import { NotFoundView } from "./NotFoundView";

/** Every address the application answers: the workspace at its three views, and a plain page for anything else. */
export const routes: RouteObject[] = [
    { path: "/", element: <WorkspaceShell /> },
    { path: "/modules/:moduleHash", element: <WorkspaceShell /> },
    { path: "/samples/:sampleHash", element: <WorkspaceShell /> },
    { path: "*", element: <NotFoundView /> },
];

export const router = createBrowserRouter(routes);
