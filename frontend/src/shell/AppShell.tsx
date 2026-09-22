import type { ReactElement } from "react";
import { useMemo } from "react";
import { useParams } from "react-router-dom";

import { useLayoutMode } from "../layout/useLayoutMode";
import { type RouteView, shellViewOf } from "../navigation/shellView";
import { useListingStepKeys } from "../navigation/useListingStepKeys";
import { useRouteFocus } from "../navigation/useRouteFocus";
import { WorkspaceShell } from "../workspace/WorkspaceShell";
import { PhoneShell } from "./phone/PhoneShell";

interface AppShellProps {
    readonly routeView: RouteView;
}

/**
 * What every address renders: the view the address names, focused through the selection store,
 * and the shell that shows it, the phone shell or the workspace as the viewport asks. Every route
 * mounts this one component, so moving between addresses keeps the shell and everything drawn
 * inside it, and Alt with an arrow steps the shown entity through its listing in either shell.
 */
export function AppShell({ routeView }: AppShellProps): ReactElement {
    const { sampleHash, moduleHash } = useParams<{ sampleHash?: string; moduleHash?: string }>();
    const view = useMemo(() => shellViewOf(routeView, { sampleHash, moduleHash }), [routeView, sampleHash, moduleHash]);
    const { layout } = useLayoutMode();
    useRouteFocus(view);
    useListingStepKeys(view);
    return layout === "phone" ? <PhoneShell view={view} /> : <WorkspaceShell view={view} />;
}
