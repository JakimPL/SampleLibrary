import type { ReactElement } from "react";

export const CLOSED_PATH = "/closed";

/** What a tab shows once the application it talked to has quit. */
export function ClosedView(): ReactElement {
    return (
        <main className="setup-page setup-page-closed">
            <section className="setup-card">
                <h1>SampleLibrary has closed</h1>
                <p className="setup-hint">You can close this tab.</p>
            </section>
        </main>
    );
}
