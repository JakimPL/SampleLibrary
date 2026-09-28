import { shortHash } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { useSamplePreview } from "./useSamplePreview";

/** A sample's name as the catalog states it, or `null` until it has answered. */
export function useSampleName(hash: string): string | null {
    const preview = useSamplePreview(hash);
    return preview.status === "success" ? preview.data.display_name : null;
}

/** The sample as a screen reader hears it: its name, the unnamed label, or the short hash until the catalog answers. */
export function spokenNameOf(hash: string, name: string | null): string {
    if (name === null) {
        return shortHash(hash);
    }
    return name === "" ? UNNAMED_SAMPLE_LABEL : name;
}
