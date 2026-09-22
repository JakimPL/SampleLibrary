import type { DockviewApi } from "dockview-react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { ThemeMenu } from "../theme/ThemeMenu";
import { ViewMenu } from "./ViewMenu";

interface TopBarProps {
    readonly api: DockviewApi | null;
}

/** The workspace's one strip of chrome: the application's name, the View menu and the theme. */
export function TopBar({ api }: TopBarProps): ReactElement {
    return (
        <header className="top-bar">
            <Link to="/" className="top-bar-title">
                SampleLibrary
            </Link>
            <ViewMenu api={api} />
            <ThemeMenu />
        </header>
    );
}
