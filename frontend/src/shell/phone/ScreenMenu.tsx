import type { ReactElement } from "react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { floatRenderingSupport } from "../../cloud/floatRendering";
import { useLayoutMode } from "../../layout/useLayoutMode";
import { DisclosureMenu } from "../../shared/overlay/DisclosureMenu";
import { ThemeMenu } from "../../theme/ThemeMenu";
import { DIAGNOSTICS_TITLE, DiagnosticsSheet } from "../DiagnosticsSheet";
import { GUIDE_TITLES, GuideSheet } from "../GuideSheet";
import { overflowPanels } from "./phoneView";

/** The menu at a tab's far end: the panels with no tab of their own, the guide to the gestures, the diagnostics, and the theme. */
export function ScreenMenu(): ReactElement {
    const { input } = useLayoutMode();
    const [guideOpen, setGuideOpen] = useState(false);
    const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);

    return (
        <>
            <DisclosureMenu label="More" className="screen-menu">
                <ul className="screen-menu-list">
                    {overflowPanels().map((panel) => (
                        <li key={panel.id}>
                            <Link to={panel.path} className="screen-menu-link">
                                {panel.title}
                            </Link>
                        </li>
                    ))}
                    <li>
                        <button
                            type="button"
                            className="screen-menu-button"
                            onClick={() => {
                                setGuideOpen(true);
                            }}
                        >
                            {GUIDE_TITLES[input]}
                        </button>
                    </li>
                    <li>
                        <button
                            type="button"
                            className="screen-menu-button"
                            onClick={() => {
                                setDiagnosticsOpen(true);
                            }}
                        >
                            {DIAGNOSTICS_TITLE}
                        </button>
                    </li>
                </ul>
                <ThemeMenu />
            </DisclosureMenu>
            {guideOpen && (
                <GuideSheet
                    input={input}
                    onClose={() => {
                        setGuideOpen(false);
                    }}
                />
            )}
            {diagnosticsOpen && (
                <DiagnosticsSheet
                    support={floatRenderingSupport()}
                    onClose={() => {
                        setDiagnosticsOpen(false);
                    }}
                />
            )}
        </>
    );
}
