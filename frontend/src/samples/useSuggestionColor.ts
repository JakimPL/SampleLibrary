import { useCallback, useMemo } from "react";

import { topLevelTags } from "../cloud/labelColoring";
import { useSuggestionTags } from "../cloud/useSuggestionTags";
import { labelColor, readLabelPaletteParameters } from "../theme/labelPalette";
import { useThemeSignal } from "../theme/useThemeSignal";
import { topLevelOf } from "./labelText";

/**
 * The color a suggested label wears: its top level's, from the rank the scoring on show gives
 * that top level, so a badge naming a sample and the point the cloud paints for it share one color.
 *
 * The tags arrive through the request cache the cloud's own legend reads, so every badge on screen
 * shares one request; until it lands, and for a top level the scoring's vocabulary leaves unranked,
 * a label has no color. Colors are read back from the theme on every theme change, the way the
 * legend's swatches are.
 */
export function useSuggestionColor(): (label: string) => string | null {
    const state = useSuggestionTags(true);
    const themeSignal = useThemeSignal();
    const colorByName = useMemo(() => {
        if (state.status !== "success") {
            return new Map<string, string>();
        }
        const parameters = readLabelPaletteParameters();
        return new Map(topLevelTags(state.data).map((tag) => [tag.name, labelColor(tag.rank, parameters)]));
        // eslint-disable-next-line react-hooks/exhaustive-deps -- the theme signal is what changes the parameters read
    }, [state, themeSignal.preference, themeSignal.systemVersion]);

    return useCallback((label: string) => colorByName.get(topLevelOf(label)) ?? null, [colorByName]);
}
