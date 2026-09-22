import "dockview-react/dist/styles/dockview.css";

import { type DockviewApi, DockviewReact, type DockviewReadyEvent, type IDockviewPanelProps } from "dockview-react";
import type { FunctionComponent, ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";

import { useMorphStore } from "../morph/morphStore";
import type { ShellView } from "../navigation/shellView";
import { withBoundary } from "../shared/ErrorBoundary";
import { PanelHost } from "../shared/panel/PanelHost";
import { TopBar } from "../shell/TopBar";
import { restoreOrBuildLayout } from "./dockviewPersistence";
import { PANEL_REGISTRY } from "./panelRegistry";
import { openAndRevealPanel, revealPanel } from "./revealPanel";

interface WorkspaceShellProps {
    readonly view: ShellView;
}

/**
 * Adapts each zero-prop panel component into the shape dockview mounts by id, ignoring the
 * `api`/`containerApi`/`params` dockview injects -- no panel in this shell needs them, since every
 * panel reads what it needs from `selectionStore` and its own feature-folder data hook instead.
 * Every panel sits in its own `PanelHost` under a boundary of its own, so one failure costs one panel.
 */
function buildDockviewComponents(): Record<string, FunctionComponent<IDockviewPanelProps>> {
    return Object.fromEntries(
        Object.values(PANEL_REGISTRY).map((definition) => {
            const PanelComponent = definition.component;
            const DockviewPanelAdapter: FunctionComponent<IDockviewPanelProps> = () =>
                withBoundary(
                    <PanelHost panelId={definition.id}>
                        <PanelComponent />
                    </PanelHost>,
                );
            return [definition.id, DockviewPanelAdapter];
        }),
    );
}

/**
 * The dockable workspace: the top bar over dockview's groups of panels. An address reveals its
 * panel or the detail of its entity once the instance is ready, and a completed morph pair brings
 * the Morph panel forward, so the sound a person just paired is one glance away.
 */
export function WorkspaceShell({ view }: WorkspaceShellProps): ReactElement {
    const components = useMemo(buildDockviewComponents, []);
    const [api, setApi] = useState<DockviewApi | null>(null);
    const pairComplete = useMorphStore((state) => state.first !== null && state.second !== null);

    useEffect(() => {
        if (api === null) {
            return;
        }
        switch (view.kind) {
            case "panel":
                openAndRevealPanel(api, PANEL_REGISTRY[view.panelId]);
                break;
            case "sample":
                revealPanel(api, "sample-detail");
                break;
            case "module":
                revealPanel(api, "module-detail");
                break;
        }
    }, [view, api]);

    useEffect(() => {
        if (pairComplete) {
            revealPanel(api, "morph");
        }
    }, [pairComplete, api]);

    function handleReady(event: DockviewReadyEvent): void {
        restoreOrBuildLayout(event.api);
        setApi(event.api);
    }

    return (
        <div className="workspace-root">
            <TopBar api={api} />
            <DockviewReact
                className="workspace-shell dockview-theme-abyss"
                components={components}
                onReady={handleReady}
                disableFloatingGroups
                singleTabMode="fullwidth"
            />
        </div>
    );
}
