import type { ReactElement } from "react";
import { Link } from "react-router-dom";

/** What an address naming no view of the library shows: that nothing lives there, and the way back to the workspace. */
export function NotFoundView(): ReactElement {
    return (
        <main className="not-found">
            <h1>Nothing lives at this address</h1>
            <p>
                <Link to="/">Back to the workspace</Link>
            </p>
        </main>
    );
}
