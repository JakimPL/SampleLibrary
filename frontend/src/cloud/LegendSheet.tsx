import type { ReactElement } from "react";
import { useMemo } from "react";

import { BottomSheet } from "../shared/overlay/BottomSheet";
import { labelColor, readLabelPaletteParameters } from "../theme/labelPalette";
import { useThemeSignal } from "../theme/useThemeSignal";
import { type ColoringMode, ColoringModeChoice } from "./ColoringModeChoice";
import type { TopLevelTag } from "./labelColoring";

interface LegendSheetProps {
    readonly mode: ColoringMode;
    readonly onModeChange: (mode: ColoringMode) => void;
    readonly tags: readonly TopLevelTag[];
    readonly painted: readonly string[];
    readonly onToggle: (name: string) => void;
    /** What the sheet says while the chosen mode has no tag to paint yet. */
    readonly emptyCaption: string;
    readonly onClose: () => void;
}

/**
 * The legend as a sheet, for a cloud too narrow to hold its chips in a row: the choice of what
 * paints the points, then every top-level tag in its color, at a finger's size, each a switch for
 * whether the cloud paints it; while the chosen mode has no tag yet, the sheet says so.
 */
export function LegendSheet({
    mode,
    onModeChange,
    tags,
    painted,
    onToggle,
    emptyCaption,
    onClose,
}: LegendSheetProps): ReactElement {
    const themeSignal = useThemeSignal();
    const colorByName = useMemo(() => {
        const parameters = readLabelPaletteParameters();
        return new Map(tags.map((tag) => [tag.name, labelColor(tag.rank, parameters)]));
        // eslint-disable-next-line react-hooks/exhaustive-deps -- the theme signal is what changes the parameters read
    }, [tags, themeSignal.preference, themeSignal.systemVersion]);

    return (
        <BottomSheet title="Legend" onClose={onClose}>
            <fieldset className="legend-sheet-mode">
                <legend>Color by</legend>
                <ColoringModeChoice mode={mode} onModeChange={onModeChange} />
            </fieldset>
            {tags.length === 0 ? (
                <p className="legend-sheet-empty">{emptyCaption}</p>
            ) : (
                <div className="legend-sheet-chips" role="group" aria-label="Painted tags">
                    {tags.map((tag) => (
                        <button
                            key={tag.name}
                            type="button"
                            className="tag-legend-entry"
                            aria-pressed={painted.includes(tag.name)}
                            onClick={() => {
                                onToggle(tag.name);
                            }}
                        >
                            <span
                                className="tag-legend-swatch"
                                style={{ background: colorByName.get(tag.name) }}
                                aria-hidden
                            />
                            <span className="tag-legend-name">{tag.name}</span>
                            <span className="tag-legend-count">{tag.sampleCount}</span>
                        </button>
                    ))}
                </div>
            )}
        </BottomSheet>
    );
}
