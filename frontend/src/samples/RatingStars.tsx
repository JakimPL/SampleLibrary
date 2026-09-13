import type { ReactElement } from "react";
import { useState } from "react";

import { classNames } from "../shared/classNames";
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
 *
 * Pointing at a star fills it and every star before it, showing the rating the click would leave
 * behind -- four out of five reads as four stars, the way the committed rating does.
 */
export function RatingStars({ rating, isSaving, onRatingChange }: RatingStarsProps): ReactElement {
    const [previewed, setPreviewed] = useState<number | null>(null);
    const shown = previewed ?? rating;

    return (
        <span
            className="rating-stars"
            role="group"
            aria-label="Rating"
            onMouseLeave={() => {
                setPreviewed(null);
            }}
        >
            {RATING_VALUES.map((value) => (
                <button
                    key={value}
                    type="button"
                    className={classNames("rating-star", shown !== null && value <= shown && "is-filled")}
                    disabled={isSaving}
                    aria-label={`Rate ${String(value)}`}
                    aria-pressed={rating !== null && value <= rating}
                    onMouseEnter={() => {
                        setPreviewed(value);
                    }}
                    onFocus={() => {
                        setPreviewed(value);
                    }}
                    onBlur={() => {
                        setPreviewed(null);
                    }}
                    onClick={() => {
                        onRatingChange(rating === value ? null : value);
                    }}
                >
                    {shown !== null && value <= shown ? FILLED_STAR : EMPTY_STAR}
                </button>
            ))}
        </span>
    );
}
