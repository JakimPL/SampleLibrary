import { createBrowserRouter, Navigate } from "react-router-dom";

import { CloudPage } from "../cloud/CloudPage";
import { ModuleDetailPage } from "../modules/ModuleDetailPage";
import { ModuleListPage } from "../modules/ModuleListPage";
import { SampleDetailPage } from "../samples/SampleDetailPage";
import { SampleListPage } from "../samples/SampleListPage";
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
            { path: "samples", element: <SampleListPage /> },
            { path: "samples/:sampleHash", element: <SampleDetailPage /> },
            { path: "stats", element: <StatsPage /> },
            { path: "cloud", element: <CloudPage /> },
        ],
    },
]);
