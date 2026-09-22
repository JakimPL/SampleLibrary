import type { DockviewApi } from "dockview-react";
import { type ReactElement, useEffect, useState } from "react";

import { floatRenderingSupport } from "../cloud/floatRendering";
import { useLayoutMode } from "../layout/useLayoutMode";
import { DisclosureMenu } from "../shared/overlay/DisclosureMenu";
import { addRegisteredPanel } from "../workspace/addPanel";
import { resetLayout } from "../workspace/dockviewPersistence";
import { PANEL_REGISTRY, type PanelDefinition, type PanelId } from "../workspace/panelRegistry";
import { DIAGNOSTICS_TITLE, DiagnosticsSheet } from "./DiagnosticsSheet";
import { GUIDE_TITLES, GuideSheet } from "./GuideSheet";

interface ViewMenuProps {
    readonly api: DockviewApi | null;
}

function isPanelId(id: string): id is PanelId {
    return id in PANEL_REGISTRY;
}

function openPanelIds(api: DockviewApi): ReadonlySet<PanelId> {
    const ids = new Set<PanelId>();
    for (const panel of api.panels) {
        if (isPanelId(panel.id)) {
            ids.add(panel.id);
        }
    }
    return ids;
}

/**
 * The menu that says which panels are open: a checkbox per registered panel, which closes it or
 * reopens it at its registered placement, and the reset that draws the first-run arrangement
 * again. Reads `PANEL_REGISTRY` generically, so a newly registered panel appears here with no
 * change to this file. The panel controls wait, disabled, until the shell's dockview instance is
 * ready. The guide to the keys and clicks, or to the gestures under touch, and the diagnostics
 * open from here as well.
 */
export function ViewMenu({ api }: ViewMenuProps): ReactElement {
    const [openIds, setOpenIds] = useState<ReadonlySet<PanelId>>(new Set());
    const [guideOpen, setGuideOpen] = useState(false);
    const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
    const { input } = useLayoutMode();

    useEffect(() => {
        if (api === null) {
            return undefined;
        }

        setOpenIds(openPanelIds(api));
        const subscription = api.onDidLayoutChange(() => {
            setOpenIds(openPanelIds(api));
        });
        return (): void => {
            subscription.dispose();
        };
    }, [api]);

    function handleToggle(definition: PanelDefinition): void {
        if (api === null) {
            return;
        }
        const panel = api.getPanel(definition.id);
        if (panel === undefined) {
            addRegisteredPanel(api, definition);
        } else {
            panel.api.close();
        }
    }

    function handleReset(): void {
        if (api !== null) {
            resetLayout(api);
        }
    }

    return (
        <>
            <DisclosureMenu label="View" className="view-menu">
                <ul className="view-menu-list">
                    {Object.values(PANEL_REGISTRY).map((definition) => (
                        <li key={definition.id}>
                            <label>
                                <input
                                    type="checkbox"
                                    checked={openIds.has(definition.id)}
                                    disabled={api === null}
                                    onChange={() => {
                                        handleToggle(definition);
                                    }}
                                />
                                {definition.title}
                            </label>
                        </li>
                    ))}
                </ul>
                <button type="button" className="view-menu-reset" disabled={api === null} onClick={handleReset}>
                    Reset layout
                </button>
                <button
                    type="button"
                    className="view-menu-reset"
                    onClick={() => {
                        setGuideOpen(true);
                    }}
                >
                    {GUIDE_TITLES[input]}
                </button>
                <button
                    type="button"
                    className="view-menu-reset"
                    onClick={() => {
                        setDiagnosticsOpen(true);
                    }}
                >
                    {DIAGNOSTICS_TITLE}
                </button>
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
