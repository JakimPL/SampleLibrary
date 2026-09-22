import type { ReactElement } from "react";
import { useMemo } from "react";
import { useParams } from "react-router-dom";

import { type RouteView, shellViewOf } from "../navigation/shellView";
import { useRouteFocus } from "../navigation/useRouteFocus";
import { WorkspaceShell } from "../workspace/WorkspaceShell";

interface AppShellProps {
    readonly routeView: RouteView;
}

/**
 * What every address renders: the view the address names, focused through the selection store,
 * and the shell that shows it. Every route mounts this one component, so moving between addresses
 * keeps the shell and everything drawn inside it.
 */
export function AppShell({ routeView }: AppShellProps): ReactElement {
    const { sampleHash, moduleHash } = useParams<{ sampleHash?: string; moduleHash?: string }>();
    const view = useMemo(() => shellViewOf(routeView, { sampleHash, moduleHash }), [routeView, sampleHash, moduleHash]);
    useRouteFocus(view);
    return <WorkspaceShell view={view} />;
}
