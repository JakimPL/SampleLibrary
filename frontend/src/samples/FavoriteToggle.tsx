import type { ReactElement } from "react";
import { useState } from "react";

import { classNames } from "../shared/classNames";

const FILLED_HEART = "♥";
const EMPTY_HEART = "♡";

interface FavoriteToggleProps {
    readonly favorite: boolean;
    readonly isSaving: boolean;
    readonly onFavoriteChange: (favorite: boolean) => void;
}

/** Where a person keeps a sample close, as one click that writes on its own.
 *
 * Pointing at the heart fills it, showing what the click would leave behind, the same way the stars
 * beside it answer to a pointer.
 */
export function FavoriteToggle({ favorite, isSaving, onFavoriteChange }: FavoriteToggleProps): ReactElement {
    const [isPointedAt, setIsPointedAt] = useState(false);
    const isShownFilled = favorite || isPointedAt;

    return (
        <button
            type="button"
            className={classNames("favorite-toggle", isShownFilled && "is-filled")}
            disabled={isSaving}
            aria-label="Favorite"
            aria-pressed={favorite}
            onMouseEnter={() => {
                setIsPointedAt(true);
            }}
            onMouseLeave={() => {
                setIsPointedAt(false);
            }}
            onFocus={() => {
                setIsPointedAt(true);
            }}
            onBlur={() => {
                setIsPointedAt(false);
            }}
            onClick={() => {
                onFavoriteChange(!favorite);
            }}
        >
            {isShownFilled ? FILLED_HEART : EMPTY_HEART}
        </button>
    );
}
