import "dockview-react/dist/styles/dockview.css";

import { type DockviewApi, DockviewReact, type DockviewReadyEvent, type IDockviewPanelProps } from "dockview-react";
import type { FunctionComponent, ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { ThemeMenu } from "../theme/ThemeMenu";
import { AddPanelMenu } from "./AddPanelMenu";
import { restoreOrBuildLayout } from "./dockviewPersistence";
import { PANEL_REGISTRY } from "./panelRegistry";
import { useSelectionStore } from "./selectionStore";

/**
 * Adapts each zero-prop panel component into the shape dockview mounts by id, ignoring the
 * `api`/`containerApi`/`params` dockview injects -- no panel in this shell needs them, since every
 * panel reads what it needs from `selectionStore` and its own feature-folder data hook instead.
 */
function buildDockviewComponents(): Record<string, FunctionComponent<IDockviewPanelProps>> {
    return Object.fromEntries(
        Object.values(PANEL_REGISTRY).map((definition) => {
            const PanelComponent = definition.component;
            const DockviewPanelAdapter: FunctionComponent<IDockviewPanelProps> = () => <PanelComponent />;
            return [definition.id, DockviewPanelAdapter];
        }),
    );
}

export function WorkspaceShell(): ReactElement {
    const { sampleHash, moduleHash } = useParams<{ sampleHash?: string; moduleHash?: string }>();
    const focusSample = useSelectionStore((state) => state.focusSample);
    const focusModule = useSelectionStore((state) => state.focusModule);
    const components = useMemo(buildDockviewComponents, []);
    const [api, setApi] = useState<DockviewApi | null>(null);

    useEffect(() => {
        if (sampleHash !== undefined) {
            focusSample(sampleHash);
        }
    }, [sampleHash, focusSample]);

    useEffect(() => {
        if (moduleHash !== undefined) {
            focusModule(moduleHash);
        }
    }, [moduleHash, focusModule]);

    function handleReady(event: DockviewReadyEvent): void {
        restoreOrBuildLayout(event.api);
        setApi(event.api);
    }

    return (
        <div className="workspace-root">
            <div className="workspace-toolbar">
                <AddPanelMenu api={api} />
                <ThemeMenu />
            </div>
            <DockviewReact
                className="workspace-shell dockview-theme-abyss"
                components={components}
                onReady={handleReady}
            />
        </div>
    );
}
