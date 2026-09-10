import type { ReactElement } from "react";
import { useMemo } from "react";

import { labelColor, readLabelPaletteParameters } from "../theme/labelPalette";
import { useThemeSignal } from "../theme/useThemeSignal";
import type { TopLevelTag } from "./labelColoring";

interface TagLegendProps {
    readonly tags: readonly TopLevelTag[];
    readonly painted: readonly string[];
    readonly onToggle: (name: string) => void;
}

const NOTHING_LABELED = "No sample carries a label yet. Labels written in a sample's detail panel appear here.";

/**
 * The legend that is also the picker: every top-level tag a person has used, most used first, each
 * in the color its rank gives it, pressed where it is painted on the cloud. Colors are read back
 * from the theme's parameters on every theme change, the same way the cloud re-reads its own, so
 * a swatch and the points it names stay one color.
 */
export function TagLegend({ tags, painted, onToggle }: TagLegendProps): ReactElement {
    const themeSignal = useThemeSignal();
    const colorByName = useMemo(() => {
        const parameters = readLabelPaletteParameters();
        return new Map(tags.map((tag) => [tag.name, labelColor(tag.rank, parameters)]));
        // eslint-disable-next-line react-hooks/exhaustive-deps -- the theme signal is what changes the parameters read
    }, [tags, themeSignal.preference, themeSignal.systemVersion]);

    if (tags.length === 0) {
        return <p className="cloud-caption">{NOTHING_LABELED}</p>;
    }

    return (
        <div className="tag-legend" role="group" aria-label="Painted tags">
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
                    <span className="tag-legend-swatch" style={{ background: colorByName.get(tag.name) }} aria-hidden />
                    <span className="tag-legend-name">{tag.name}</span>
                    <span className="tag-legend-count">{tag.sampleCount}</span>
                </button>
            ))}
        </div>
    );
}
