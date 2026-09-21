import type { ReactElement } from "react";
import { Link, useRouteError } from "react-router-dom";

import { ErrorNotice } from "../shared/ErrorNotice";
import { describeError } from "../shared/fetchState";

/** What a view that failed to render shows: what broke, and the way back to the workspace. */
export function RouteErrorView(): ReactElement {
    const error = useRouteError();
    return (
        <main className="route-error">
            <h1>This view stopped short</h1>
            <ErrorNotice message={describeError(error)} />
            <p>
                <Link to="/">Back to the workspace</Link>
            </p>
        </main>
    );
}
