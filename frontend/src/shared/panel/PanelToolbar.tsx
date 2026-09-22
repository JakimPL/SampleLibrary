import type { ReactElement, ReactNode } from "react";
import { useRef } from "react";

import { useContainerWidth } from "../../layout/useContainerWidth";
import { DisclosureMenu } from "../overlay/DisclosureMenu";

/** Below this width the secondary controls fold into a menu, leaving the primary one its room. */
export const TOOLBAR_COLLAPSE_WIDTH_PX = 420;

interface PanelToolbarProps {
    /** The control that stays in the row whatever the width, such as a filter field. */
    readonly primary: ReactNode;
    /** The controls that fold into a menu when the row is narrow. */
    readonly secondary: ReactNode;
    /** What the toolbar reports at its far end, such as a count. */
    readonly status: ReactNode;
}

/**
 * One row of controls over a listing. At full width the secondary controls sit beside the primary
 * one; in a narrow panel they fold into a menu so the primary control keeps its room, and the
 * status wraps under them.
 */
export function PanelToolbar({ primary, secondary, status }: PanelToolbarProps): ReactElement {
    const rootRef = useRef<HTMLDivElement | null>(null);
    const width = useContainerWidth(rootRef);
    const collapsed = width !== null && width < TOOLBAR_COLLAPSE_WIDTH_PX;

    return (
        <div className="panel-filter panel-toolbar" ref={rootRef}>
            <div className="panel-toolbar-primary">{primary}</div>
            {collapsed ? (
                <DisclosureMenu label="Filters" className="panel-toolbar-menu">
                    {secondary}
                </DisclosureMenu>
            ) : (
                <div className="panel-toolbar-secondary">{secondary}</div>
            )}
            <div className="panel-toolbar-status">{status}</div>
        </div>
    );
}
