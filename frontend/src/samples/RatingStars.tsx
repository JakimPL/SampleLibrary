import type { ReactElement } from "react";

import { EMPTY_STAR, FILLED_STAR, RATING_VALUES } from "./rating";

interface RatingStarsProps {
    readonly rating: number | null;
    readonly isSaving: boolean;
    readonly onRatingChange: (rating: number | null) => void;
}

/**
 * Where a person says what they think of a sample, on a scale of one to five.
 *
 * Each star writes straight away rather than waiting for a save: a rating is one click, and a
 * listener working through a library makes many of them. Clicking the star a sample already sits at
 * takes the rating back, which is the only gesture that would otherwise need a control of its own.
 */
export function RatingStars({ rating, isSaving, onRatingChange }: RatingStarsProps): ReactElement {
    return (
        <span className="rating-stars" role="group" aria-label="Rating">
            {RATING_VALUES.map((value) => (
                <button
                    key={value}
                    type="button"
                    className="rating-star"
                    disabled={isSaving}
                    aria-label={`Rate ${String(value)}`}
                    aria-pressed={rating !== null && value <= rating}
                    onClick={() => {
                        onRatingChange(rating === value ? null : value);
                    }}
                >
                    {rating !== null && value <= rating ? FILLED_STAR : EMPTY_STAR}
                </button>
            ))}
        </span>
    );
}
