/** The scale a person rates samples on, matching the bounds the catalog enforces. */
export const MINIMUM_RATING = 1;
export const MAXIMUM_RATING = 5;

export const RATING_VALUES: readonly number[] = Array.from(
    { length: MAXIMUM_RATING - MINIMUM_RATING + 1 },
    (_unused, index) => MINIMUM_RATING + index,
);

export const FILLED_STAR = "★";
export const EMPTY_STAR = "☆";
