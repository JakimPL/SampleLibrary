import { requestJson } from "./client";
import type { components } from "./schema";

export type CloudPoint = components["schemas"]["SampleCloudPoint"];
export type ModuleCloudPoint = components["schemas"]["ModuleCloudCoordinate"];

export async function getCloud(): Promise<readonly CloudPoint[]> {
    return requestJson<readonly CloudPoint[]>("/cloud");
}

export async function getModuleCloud(): Promise<readonly ModuleCloudPoint[]> {
    return requestJson<readonly ModuleCloudPoint[]>("/cloud/modules");
}
