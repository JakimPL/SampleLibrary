import { getModuleCloud, type ModuleCloudPoint } from "../api/cloud";
import type { FetchState } from "../shared/fetchState";
import { useFetch } from "../shared/useFetch";

const NO_DEPENDENCIES: readonly unknown[] = [];

export function useModuleCloud(): FetchState<readonly ModuleCloudPoint[]> {
    return useFetch(getModuleCloud, NO_DEPENDENCIES);
}
