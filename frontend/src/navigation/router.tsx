import { createBrowserRouter, Navigate } from "react-router-dom";

import { ModuleDetailPage } from "../modules/ModuleDetailPage";
import { ModuleListPage } from "../modules/ModuleListPage";
import { SampleDetailPage } from "../samples/SampleDetailPage";
import { StatsPage } from "../stats/StatsPage";
import { Layout } from "./Layout";

export const router = createBrowserRouter([
    {
        path: "/",
        element: <Layout />,
        children: [
            { index: true, element: <Navigate to="/modules" replace /> },
            { path: "modules", element: <ModuleListPage /> },
            { path: "modules/:moduleHash", element: <ModuleDetailPage /> },
            { path: "samples/:sampleHash", element: <SampleDetailPage /> },
            { path: "stats", element: <StatsPage /> },
        ],
    },
]);
