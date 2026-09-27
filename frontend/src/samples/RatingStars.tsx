import type { ReactElement } from "react";
import { useState } from "react";

import { useLayoutMode } from "../layout/useLayoutMode";
import { classNames } from "../shared/classNames";
import { EMPTY_STAR, FILLED_STAR, RATING_VALUES } from "./rating";

interface RatingStarsProps {
    readonly rating: number | null;
    /** Records a new rating; null where the person here may only see it. */
    readonly onRatingChange: ((rating: number | null) => void) | null;
}

/**
 * Where a person says what they think of a sample, on a scale of one to five.
 *
 * Each star writes straight away rather than waiting for a save: a rating is one click, and a
 * listener working through a library makes many of them. Clicking the star a sample already sits at
 * takes the rating back, which is the only gesture that would otherwise need a control of its own.
 *
 * Pointing at a star fills it and every star before it, showing the rating the click would leave
 * behind -- four out of five reads as four stars, the way the committed rating does. A finger
 * points at nothing before it taps, so under touch the stars answer to the tap alone. Where the person
 * here may only see the rating, the stars show it and take no clicks.
 */
export function RatingStars({ rating, onRatingChange }: RatingStarsProps): ReactElement {
    if (onRatingChange === null) {
        return <ShownRating rating={rating} />;
    }
    return <RatingButtons rating={rating} onRatingChange={onRatingChange} />;
}

function ShownRating({ rating }: { readonly rating: number | null }): ReactElement {
    return (
        <span
            className="rating-stars is-read-only"
            role="img"
            aria-label={rating === null ? "Not rated" : `Rated ${String(rating)} of ${String(RATING_VALUES.length)}`}
        >
            {RATING_VALUES.map((value) => (
                <span
                    key={value}
                    className={classNames(
                        "rating-star is-read-only",
                        rating !== null && value <= rating && "is-filled",
                    )}
                >
                    {rating !== null && value <= rating ? FILLED_STAR : EMPTY_STAR}
                </span>
            ))}
        </span>
    );
}

function RatingButtons({
    rating,
    onRatingChange,
}: {
    readonly rating: number | null;
    readonly onRatingChange: (rating: number | null) => void;
}): ReactElement {
    const [previewed, setPreviewed] = useState<number | null>(null);
    const { input } = useLayoutMode();
    const previews = input === "pointer";
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
                    aria-label={`Rate ${String(value)}`}
                    aria-pressed={rating !== null && value <= rating}
                    onMouseEnter={() => {
                        if (previews) {
                            setPreviewed(value);
                        }
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
