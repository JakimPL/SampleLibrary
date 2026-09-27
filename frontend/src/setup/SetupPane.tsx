import type { ReactElement, ReactNode } from "react";

interface SetupPaneProps {
    readonly title: string;
    readonly titleId: string;
    readonly children: ReactNode;
    /** The pane's fixed bottom row: its message line and its buttons. */
    readonly footer: ReactNode;
}

/**
 * One of the setup page's two panels, drawn as a workspace panel: a tab naming it, a body that
 * scrolls on its own, and a footer that keeps its place whatever the body holds.
 */
export function SetupPane({ title, titleId, children, footer }: SetupPaneProps): ReactElement {
    return (
        <section className="setup-pane" aria-labelledby={titleId}>
            <header className="setup-pane-tab">
                <h2 id={titleId}>{title}</h2>
            </header>
            <div className="setup-pane-body">{children}</div>
            <footer className="setup-pane-footer">{footer}</footer>
        </section>
    );
}
