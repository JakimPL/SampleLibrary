import { getCurationAccess } from "../api/curation";
import { useFetch } from "../shared/useFetch";

export const CURATION_ACCESS_CACHE_KEY = "curation-access";

const NO_DEPENDENCIES: readonly unknown[] = [];

/** What a page may show and offer of a person's labels, ratings and favorites. */
export interface CurationView {
    /** Whether the labels, ratings and favorites a person decided are shown at all. */
    readonly curationShown: boolean;
    /** Whether the person here may change them. */
    readonly labelEditing: boolean;
}

const NOTHING_SHOWN: CurationView = { curationShown: false, labelEditing: false };

/**
 * What the server lets this page show and change of a person's decisions about samples.
 *
 * Only the SampleLibrary app on its own computer records them, and a site on the internet shows
 * none of them. Both answers are false until the server has given them, so a page never shows a
 * control the server would refuse, or a decision it holds back.
 */
export function useCurationAccess(): CurationView {
    const state = useFetch(getCurationAccess, NO_DEPENDENCIES, { cacheKey: CURATION_ACCESS_CACHE_KEY });
    if (state.status !== "success") {
        return NOTHING_SHOWN;
    }
    return { curationShown: state.data.curation_shown, labelEditing: state.data.label_editing };
}
