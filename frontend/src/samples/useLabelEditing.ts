import { getLabelEditing } from "../api/curation";
import { useFetch } from "../shared/useFetch";

export const LABEL_EDITING_CACHE_KEY = "label-editing";

const NO_DEPENDENCIES: readonly unknown[] = [];

/**
 * Whether the person here may change labels, ratings and favorites.
 *
 * Only the SampleLibrary app on its own computer records them; a deployed site shows them as they
 * are. The answer is false until the server has given it, so a page never shows a control the
 * server would refuse.
 */
export function useLabelEditing(): boolean {
    const state = useFetch(getLabelEditing, NO_DEPENDENCIES, { cacheKey: LABEL_EDITING_CACHE_KEY });
    return state.status === "success" && state.data.label_editing;
}
