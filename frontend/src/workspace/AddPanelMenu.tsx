import type { DockviewApi } from "dockview-react";
import { type ReactElement, useEffect, useState } from "react";

import { PANEL_REGISTRY, type PanelId } from "./panelRegistry";

interface AddPanelMenuProps {
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
 * Lets a panel closed via its own tab's close button be reopened, reading `PANEL_REGISTRY`
 * generically -- a newly registered panel becomes addable here with no change to this file. A
 * reopened panel returns to its registered `placement` when that placement's reference panel is
 * still open, the same rule `buildDefaultLayout` uses for the shell's first-run arrangement.
 * Renders nothing once every registered panel is already open, and nothing before the shell's
 * dockview instance is ready.
 */
export function AddPanelMenu({ api }: AddPanelMenuProps): ReactElement | null {
    const [openIds, setOpenIds] = useState<ReadonlySet<PanelId>>(new Set());

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

    if (api === null) {
        return null;
    }

    const closedPanels = Object.values(PANEL_REGISTRY).filter((definition) => !openIds.has(definition.id));
    if (closedPanels.length === 0) {
        return null;
    }

    function handleAdd(panelId: PanelId): void {
        const definition = PANEL_REGISTRY[panelId];
        // Placing a re-added panel relative to its reference only makes sense while that reference
        // is actually open -- otherwise this falls back to dockview's own default placement, same
        // as if this panel had no preferred placement at all.
        const placement =
            definition.placement !== null && openIds.has(definition.placement.referencePanel)
                ? definition.placement
                : null;
        api?.addPanel({
            id: definition.id,
            component: definition.id,
            title: definition.title,
            ...(placement !== null ? { position: placement } : {}),
        });
    }

    return (
        <div className="add-panel-menu">
            <span className="add-panel-label">Add panel</span>
            {closedPanels.map((definition) => (
                <button
                    key={definition.id}
                    type="button"
                    onClick={() => {
                        handleAdd(definition.id);
                    }}
                >
                    {definition.title}
                </button>
            ))}
        </div>
    );
}
