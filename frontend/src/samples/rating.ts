/** The scale a person rates samples on, matching the bounds the catalog enforces. */
export const MINIMUM_RATING = 1;
export const MAXIMUM_RATING = 5;

export const RATING_VALUES: readonly number[] = Array.from(
    { length: MAXIMUM_RATING - MINIMUM_RATING + 1 },
    (_unused, index) => MINIMUM_RATING + index,
);

const FILLED_STAR = "★";
const EMPTY_STAR = "☆";

/** A rating written out as stars, for reading at a glance in a list row. */
export function ratingGlyphs(rating: number | null): string {
    if (rating === null) {
        return "";
    }

    return RATING_VALUES.map((value) => (value <= rating ? FILLED_STAR : EMPTY_STAR)).join("");
}

export { EMPTY_STAR, FILLED_STAR };
