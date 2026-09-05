import type { ReactElement } from "react";
import { RouterProvider } from "react-router-dom";

import { router } from "./navigation/router";

export function App(): ReactElement {
    return <RouterProvider router={router} />;
}
