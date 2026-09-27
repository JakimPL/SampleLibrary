import { type ReactElement, useState } from "react";

import { floatRenderingSupport } from "../cloud/floatRendering";
import { useLayoutMode } from "../layout/useLayoutMode";
import { Button } from "../shared/controls/Button";
import { DisclosureMenu } from "../shared/overlay/DisclosureMenu";
import { DIAGNOSTICS_TITLE, DiagnosticsSheet } from "./DiagnosticsSheet";
import { GUIDE_TITLES, GuideSheet } from "./GuideSheet";

/** The guide to the keys and clicks, or to the gestures under touch, and what this browser can draw. */
export function HelpMenu(): ReactElement {
    const [guideOpen, setGuideOpen] = useState(false);
    const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
    const { input } = useLayoutMode();

    return (
        <>
            <DisclosureMenu label="Help" className="help-menu" variant="quiet">
                <Button
                    variant="quiet"
                    wide
                    className="menu-action"
                    onClick={() => {
                        setGuideOpen(true);
                    }}
                >
                    {GUIDE_TITLES[input]}
                </Button>
                <Button
                    variant="quiet"
                    wide
                    className="menu-action"
                    onClick={() => {
                        setDiagnosticsOpen(true);
                    }}
                >
                    {DIAGNOSTICS_TITLE}
                </Button>
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
