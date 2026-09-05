import { type EntityRef, useSelectionStore } from "./selectionStore";

/**
 * Whether `entity` is the shell's currently highlighted row or point.
 *
 * Selecting down to a `boolean` (rather than reading `highlighted` directly) means a row only
 * re-renders when its own highlighted-ness actually flips, not on every highlight change
 * elsewhere in the shell -- the difference that matters once highlighting follows hover, not
 * only clicks.
 */
export function useIsHighlighted(entity: EntityRef): boolean {
    return useSelectionStore(
        (state) => state.highlighted?.kind === entity.kind && state.highlighted.hash === entity.hash,
    );
}
