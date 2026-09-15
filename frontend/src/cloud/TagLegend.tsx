import type { ReactElement } from "react";
import { useMemo, useState } from "react";

import { labelColor, readLabelPaletteParameters } from "../theme/labelPalette";
import { useThemeSignal } from "../theme/useThemeSignal";
import type { TopLevelTag } from "./labelColoring";

interface TagLegendProps {
    readonly tags: readonly TopLevelTag[];
    readonly painted: readonly string[];
    readonly onToggle: (name: string) => void;
    /** What the strip says while no sample carries a tag of this legend's kind. */
    readonly emptyCaption: string;
}

const COLLAPSE_LABEL = "Painted only";

/**
 * The legend that is also the picker: the top-level tags painted on the cloud, most used first,
 * each in the color its rank gives it, with the rest of the vocabulary one toggle away. Showing
 * the painted tags alone at rest is what keeps the strip to a row or two however many tags a
 * person has written; expanded, it lists every tag in the same order, so a chip keeps its place
 * whether or not its neighbors are shown. Colors are read back from the theme's parameters on
 * every theme change, the same way the cloud re-reads its own, so a swatch and the points it
 * names stay one color.
 */
export function TagLegend({ tags, painted, onToggle, emptyCaption }: TagLegendProps): ReactElement {
    const [expanded, setExpanded] = useState(false);
    const themeSignal = useThemeSignal();
    const colorByName = useMemo(() => {
        const parameters = readLabelPaletteParameters();
        return new Map(tags.map((tag) => [tag.name, labelColor(tag.rank, parameters)]));
        // eslint-disable-next-line react-hooks/exhaustive-deps -- the theme signal is what changes the parameters read
    }, [tags, themeSignal.preference, themeSignal.systemVersion]);

    if (tags.length === 0) {
        return <p className="cloud-caption">{emptyCaption}</p>;
    }

    const paintedTags = tags.filter((tag) => painted.includes(tag.name));
    const hiddenCount = tags.length - paintedTags.length;
    const shown = expanded ? tags : paintedTags;

    return (
        <div className="tag-legend" role="group" aria-label="Painted tags">
            {shown.map((tag) => (
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
            {hiddenCount > 0 && (
                <button
                    type="button"
                    className="tag-legend-toggle"
                    aria-expanded={expanded}
                    onClick={() => {
                        setExpanded((current) => !current);
                    }}
                >
                    {expanded ? COLLAPSE_LABEL : `+${String(hiddenCount)} more`}
                </button>
            )}
        </div>
    );
}
