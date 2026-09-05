import { requestJson } from "./client";
import type { components } from "./schema";

export type Module = components["schemas"]["Module"];
export type ModuleDetail = components["schemas"]["ModuleDetail"];
export type ModulePage = components["schemas"]["Page_Module_"];
export type TrackerFormat = components["schemas"]["TrackerFormat"];

export interface ListModulesParams {
    readonly limit: number;
    readonly offset: number;
    readonly tracker: TrackerFormat | null;
}

export async function listModules(params: ListModulesParams): Promise<ModulePage> {
    const query = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
    if (params.tracker !== null) {
        query.set("tracker", params.tracker);
    }
    return requestJson<ModulePage>(`/modules?${query.toString()}`);
}

export async function getModule(moduleHash: string): Promise<ModuleDetail> {
    return requestJson<ModuleDetail>(`/modules/${moduleHash}`);
}
