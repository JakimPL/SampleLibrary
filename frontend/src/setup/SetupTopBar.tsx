import type { ReactElement } from "react";

import { Button } from "../shared/controls/Button";
import { ThemeMenu } from "../theme/ThemeMenu";
import { SetupMessage } from "./SetupMessage";

interface SetupTopBarProps {
    /** What the application has to say about itself, such as a quit it refused. */
    readonly notice: string | null;
    readonly quitEnabled: boolean;
    readonly onQuit: () => void;
}

/**
 * The workspace's bar over the setup page: the name, a line reserved for the application's
 * notices, the theme, and Quit in the corner where the workspace keeps its Library menu.
 */
export function SetupTopBar({ notice, quitEnabled, onQuit }: SetupTopBarProps): ReactElement {
    return (
        <header className="top-bar">
            <span className="top-bar-title">SampleRipper</span>
            <SetupMessage message={notice === null ? null : { text: notice, tone: "error" }} className="setup-notice" />
            <ThemeMenu />
            <Button variant="secondary" disabled={!quitEnabled} onClick={onQuit}>
                Quit
            </Button>
        </header>
    );
}
