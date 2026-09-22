import type { AnnotationChanges, AnnotationDecisions } from "../api/curation";
import { RATING_VALUES } from "./rating";

const FAVORITE_KEY = "f";

/**
 * The decision a key names on a focused sample row: F flips the favorite mark, and a digit from
 * one to five rates the sample, or takes the rating back when it already stands there, as the
 * star itself does. Any other key names nothing.
 */
export function annotationKeyChange(key: string, decisions: AnnotationDecisions): AnnotationChanges | null {
    if (key.toLowerCase() === FAVORITE_KEY) {
        return { favorite: !decisions.favorite };
    }
    const rating = RATING_VALUES.find((value) => String(value) === key);
    if (rating !== undefined) {
        return { rating: decisions.rating === rating ? null : rating };
    }
    return null;
}
