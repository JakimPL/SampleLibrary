import { requestJson } from "./client";
import type { components } from "./schema";

export type CloudPoint = components["schemas"]["SampleCloudCoordinate"];

export async function getCloud(): Promise<readonly CloudPoint[]> {
    return requestJson<readonly CloudPoint[]>("/cloud");
}
