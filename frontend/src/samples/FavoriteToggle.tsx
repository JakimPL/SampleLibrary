import type { ReactElement } from "react";

const FILLED_HEART = "♥";
const EMPTY_HEART = "♡";

interface FavoriteToggleProps {
    readonly favorite: boolean;
    readonly isSaving: boolean;
    readonly onFavoriteChange: (favorite: boolean) => void;
}

/** Where a person keeps a sample close, as one click that writes on its own. */
export function FavoriteToggle({ favorite, isSaving, onFavoriteChange }: FavoriteToggleProps): ReactElement {
    return (
        <button
            type="button"
            className="favorite-toggle"
            disabled={isSaving}
            aria-label="Favorite"
            aria-pressed={favorite}
            onClick={() => {
                onFavoriteChange(!favorite);
            }}
        >
            {favorite ? FILLED_HEART : EMPTY_HEART}
        </button>
    );
}
