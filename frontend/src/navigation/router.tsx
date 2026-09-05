import { createBrowserRouter } from "react-router-dom";

import { WorkspaceShell } from "../workspace/WorkspaceShell";

export const router = createBrowserRouter([
    { path: "/", element: <WorkspaceShell /> },
    { path: "/modules/:moduleHash", element: <WorkspaceShell /> },
    { path: "/samples/:sampleHash", element: <WorkspaceShell /> },
]);
