import type { ReactElement } from "react";
import { RouterProvider } from "react-router-dom";

import { useLayoutAttributes } from "./layout/layoutAttributes";
import { router } from "./navigation/router";

export function App(): ReactElement {
    useLayoutAttributes();
    return <RouterProvider router={router} />;
}
