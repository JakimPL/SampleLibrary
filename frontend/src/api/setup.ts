import { requestJson, sendJson } from "./client";
import type { components } from "./setupSchema";

export type SetupState = components["schemas"]["SetupState"];
export type LibraryStatus = SetupState["status"];
export type LibrarySources = components["schemas"]["LibrarySources"];
export type BuildView = components["schemas"]["JobView"];
export type BuildTarget = BuildView["target"];
export type BuildStep = components["schemas"]["StepView"];
export type StepState = BuildStep["state"];
export type FolderListing = components["schemas"]["FolderListing"];
export type Place = components["schemas"]["Place"];

// Kept equal to `SETUP_PREFIX` in `src/samplelibrary/app/asgi.py`, relative to the API's root.
const SETUP_PATH = "/setup";

export async function getSetupState(): Promise<SetupState> {
    return requestJson<SetupState>(`${SETUP_PATH}/state`);
}

export async function chooseSources(sources: LibrarySources): Promise<SetupState> {
    return sendJson<SetupState>(`${SETUP_PATH}/sources`, { method: "PUT", body: sources });
}

export async function startBuild(target: BuildTarget): Promise<SetupState> {
    return sendJson<SetupState>(`${SETUP_PATH}/builds`, { method: "POST", body: { target } });
}

export async function cancelBuild(): Promise<SetupState> {
    return sendJson<SetupState>(`${SETUP_PATH}/builds/cancel`, { method: "POST", body: null });
}

export async function getPlaces(): Promise<readonly Place[]> {
    return requestJson<readonly Place[]>(`${SETUP_PATH}/places`);
}

export async function getFolder(path: string): Promise<FolderListing> {
    return requestJson<FolderListing>(`${SETUP_PATH}/folders?${new URLSearchParams({ path }).toString()}`);
}

export async function quitApplication(): Promise<void> {
    await sendJson<null>(`${SETUP_PATH}/quit`, { method: "POST", body: null });
}
