import type { ReactElement, ReactNode } from "react";

import type { PanelId } from "../../workspace/panelRegistry";

interface PanelHostProps {
    readonly panelId: PanelId;
    readonly children: ReactNode;
}

/**
 * The box every panel renders in, whichever shell mounts it: the scroll container for the panel's
 * own overflow, and the container its stylesheet rules query, so a panel fits the width it was
 * given rather than the window's.
 */
export function PanelHost({ panelId, children }: PanelHostProps): ReactElement {
    return (
        <div className="panel-host" data-panel={panelId}>
            {children}
        </div>
    );
}
