import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { DisclosureMenu } from "../../shared/overlay/DisclosureMenu";
import { ThemeMenu } from "../../theme/ThemeMenu";
import { overflowPanels } from "./phoneView";

/** The menu at a tab's far end: the panels with no tab of their own, and the theme. */
export function ScreenMenu(): ReactElement {
    return (
        <DisclosureMenu label="More" className="screen-menu">
            <ul className="screen-menu-list">
                {overflowPanels().map((panel) => (
                    <li key={panel.id}>
                        <Link to={panel.path} className="screen-menu-link">
                            {panel.title}
                        </Link>
                    </li>
                ))}
            </ul>
            <ThemeMenu />
        </DisclosureMenu>
    );
}
