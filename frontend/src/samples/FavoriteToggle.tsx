import type { ReactElement } from "react";
import { useState } from "react";

import { useLayoutMode } from "../layout/useLayoutMode";
import { classNames } from "../shared/classNames";

const FILLED_HEART = "♥";
const EMPTY_HEART = "♡";

interface FavoriteToggleProps {
    readonly favorite: boolean;
    /** Records the new mark; null where the person here may only see it. */
    readonly onFavoriteChange: ((favorite: boolean) => void) | null;
}

/** Where a person keeps a sample close, as one click that writes on its own.
 *
 * Pointing at the heart fills it, showing what the click would leave behind, the same way the stars
 * beside it answer to a pointer; under touch the heart answers to the tap alone. Where the person here
 * may only see the mark, the heart shows it and takes no clicks.
 */
export function FavoriteToggle({ favorite, onFavoriteChange }: FavoriteToggleProps): ReactElement {
    if (onFavoriteChange === null) {
        return (
            <span
                className={classNames("favorite-toggle is-read-only", favorite && "is-filled")}
                role="img"
                aria-label={favorite ? "Favorite" : "Not a favorite"}
            >
                {favorite ? FILLED_HEART : EMPTY_HEART}
            </span>
        );
    }
    return <FavoriteButton favorite={favorite} onFavoriteChange={onFavoriteChange} />;
}

function FavoriteButton({
    favorite,
    onFavoriteChange,
}: {
    readonly favorite: boolean;
    readonly onFavoriteChange: (favorite: boolean) => void;
}): ReactElement {
    const [isPointedAt, setIsPointedAt] = useState(false);
    const { input } = useLayoutMode();
    const isShownFilled = favorite || isPointedAt;

    return (
        <button
            type="button"
            className={classNames("favorite-toggle", isShownFilled && "is-filled")}
            aria-label="Favorite"
            aria-pressed={favorite}
            onMouseEnter={() => {
                if (input === "pointer") {
                    setIsPointedAt(true);
                }
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
