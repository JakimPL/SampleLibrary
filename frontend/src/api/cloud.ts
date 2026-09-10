import { requestJson } from "./client";
import type { components } from "./schema";

export type CloudPoint = components["schemas"]["SampleCloudPoint"];
export type ModuleCloudPoint = components["schemas"]["ModuleCloudCoordinate"];
/** What a person decided one sample is: its tag paths, in the order they wrote them. */
export type CloudLabel = components["schemas"]["CloudLabel"];

export async function getCloud(): Promise<readonly CloudPoint[]> {
    return requestJson<readonly CloudPoint[]>("/cloud");
}

export async function getModuleCloud(): Promise<readonly ModuleCloudPoint[]> {
    return requestJson<readonly ModuleCloudPoint[]>("/cloud/modules");
}

/**
 * Every labeled sample's tags, fetched apart from the points: a few hundred rows that change with
 * every label written, against a hundred thousand points that change only when the embedding does.
 */
export async function getCloudLabels(): Promise<readonly CloudLabel[]> {
    return requestJson<readonly CloudLabel[]>("/cloud/labels");
}
