import { type ReactElement, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { CloudLabel, CloudPoint, CloudSuggestion, ModuleCloudPoint } from "../../api/cloud";
import { type CloudLink, CloudView } from "../../cloud/CloudView";
import type { CloudEntityPoint } from "../../cloud/geometry";
import {
    defaultPaintedTags,
    labelColoring,
    type PointColoring,
    type TopLevelTag,
    topLevelTags,
} from "../../cloud/labelColoring";
import { TagLegend } from "../../cloud/TagLegend";
import { useCloud } from "../../cloud/useCloud";
import { useCloudLabels } from "../../cloud/useCloudLabels";
import { useCloudSuggestions } from "../../cloud/useCloudSuggestions";
import { useModuleCloud } from "../../cloud/useModuleCloud";
import { useSuggestionTags } from "../../cloud/useSuggestionTags";
import { morphPreview } from "../../morph/morphPreview";
import { useMorphStore } from "../../morph/morphStore";
import { useMorphStatus } from "../../morph/useMorphStatus";
import { samplePreview, useAudioPreview } from "../../samples/useAudioPreview";
import { useLabelTags } from "../../samples/useLabelTags";
import { ErrorNotice } from "../../shared/ErrorNotice";
import type { FetchState } from "../../shared/fetchState";
import { Loading } from "../../shared/Loading";
import { type EntityRef, useSelectionStore } from "../selectionStore";
import { entityRoute } from "../useEntityRowInteractions";
import { CloudHoverTooltip } from "./CloudHoverTooltip";

type CloudTab = "samples" | "modules";
type ColoringMode = "category" | "label" | "suggestion";

const CATEGORY_COLORING: PointColoring = { kind: "category" };
const NO_TAGS: readonly TopLevelTag[] = [];

interface HoveredPoint {
    readonly entity: EntityRef;
    readonly x: number;
    readonly y: number;
}

const MODULE_TAB_CAPTION = "Preliminary layout — real positions await a spectral-distance embedding.";

function samplePoints(coordinates: readonly CloudPoint[]): readonly CloudEntityPoint[] {
    return coordinates.map((coordinate) => ({
        ref: { kind: "sample", hash: coordinate.sample_hash },
        x: coordinate.x,
        y: coordinate.y,
        category: coordinate.category,
        ...(coordinate.playback_rate_hz !== null && { playbackRateHz: coordinate.playback_rate_hz }),
    }));
}

function modulePoints(coordinates: readonly ModuleCloudPoint[]): readonly CloudEntityPoint[] {
    return coordinates.map((coordinate) => ({
        ref: { kind: "module", hash: coordinate.module_hash },
        x: coordinate.x,
        y: coordinate.y,
    }));
}

/**
 * Both tabs' coordinates are fetched unconditionally, not only once their tab is first opened --
 * each payload is a handful of floats per entity, cheap enough that switching tabs never has to
 * wait on a request the other tab could have already finished.
 *
 * Each tab's points are memoized on its own fetch state, which `useFetch` only ever replaces once
 * a request genuinely settles again -- otherwise `samplePoints`/`modulePoints` would map a fresh
 * array (and fresh point objects) on every render of this panel, including ones unrelated to the
 * coordinates themselves (a hover, the other tab's own fetch resolving). `CloudView` depends on
 * referential stability here: it redraws its whole scatterplot whenever this array's identity
 * changes, so an unstable identity redraws far more often than the data actually does.
 */
function useActiveCloudPoints(tab: CloudTab): FetchState<readonly CloudEntityPoint[]> {
    const sampleState = useCloud();
    const moduleState = useModuleCloud();

    const samplePointsState = useMemo(
        (): FetchState<readonly CloudEntityPoint[]> =>
            sampleState.status === "success"
                ? { status: "success", data: samplePoints(sampleState.data) }
                : sampleState,
        [sampleState],
    );
    const modulePointsState = useMemo(
        (): FetchState<readonly CloudEntityPoint[]> =>
            moduleState.status === "success"
                ? { status: "success", data: modulePoints(moduleState.data) }
                : moduleState,
        [moduleState],
    );

    return tab === "samples" ? samplePointsState : modulePointsState;
}

/** A sample's first suggestion in the shape the label coloring paints by: one path, the way a written label's first tag is. */
function suggestionsAsLabels(suggestions: readonly CloudSuggestion[]): readonly CloudLabel[] {
    return suggestions.map((suggestion) => ({ sample_hash: suggestion.sample_hash, paths: [suggestion.path] }));
}

/**
 * How the sample points are colored. Under the label mode the tags a person has painted are their
 * own choice once they touch the legend, and the most used ones until then -- so a vocabulary that
 * grows during a labeling session keeps showing whatever was chosen, and a fresh session shows
 * the tags with the most to show. The suggestion mode paints the same way from what the listening
 * model heard, its own legend drawn from the scoring's vocabulary; a chosen set belongs to one mode,
 * so switching starts the other from its own most-used tags. A mode's sources are fetched the first
 * time it is chosen and kept for the session, so the category mode, which needs none of them,
 * costs nothing beyond the points.
 */
function useSampleColoring(mode: ColoringMode): {
    readonly coloring: PointColoring;
    readonly tags: readonly TopLevelTag[];
    readonly painted: readonly string[];
    readonly togglePainted: (name: string) => void;
} {
    const labelsState = useCloudLabels(mode === "label");
    const tagsState = useLabelTags(mode === "label");
    const suggestionsState = useCloudSuggestions(mode === "suggestion");
    const suggestionTagsState = useSuggestionTags(mode === "suggestion");
    const [chosen, setChosen] = useState<readonly string[] | null>(null);
    useEffect(() => {
        setChosen(null);
    }, [mode]);
    const tags = useMemo(() => {
        const source = mode === "suggestion" ? suggestionTagsState : tagsState;
        return source.status === "success" ? topLevelTags(source.data) : NO_TAGS;
    }, [mode, tagsState, suggestionTagsState]);
    const painted = useMemo(() => chosen ?? defaultPaintedTags(tags), [chosen, tags]);
    const coloring = useMemo((): PointColoring => {
        if (mode === "label" && labelsState.status === "success") {
            return labelColoring(labelsState.data, tags, painted);
        }
        if (mode === "suggestion" && suggestionsState.status === "success") {
            return labelColoring(suggestionsAsLabels(suggestionsState.data), tags, painted);
        }
        return CATEGORY_COLORING;
    }, [mode, labelsState, suggestionsState, tags, painted]);

    function togglePainted(name: string): void {
        setChosen(painted.includes(name) ? painted.filter((candidate) => candidate !== name) : [...painted, name]);
    }

    return { coloring, tags, painted, togglePainted };
}

export function CloudPanel(): ReactElement {
    const [tab, setTab] = useState<CloudTab>("samples");
    const [mode, setMode] = useState<ColoringMode>("category");
    const [hovered, setHovered] = useState<HoveredPoint | null>(null);
    const state = useActiveCloudPoints(tab);
    const { coloring, tags, painted, togglePainted } = useSampleColoring(mode);
    const navigate = useNavigate();
    const highlighted = useSelectionStore((selection) => selection.highlighted);
    const focusedSampleHash = useSelectionStore((selection) => selection.focusedSampleHash);
    const highlightEntity = useSelectionStore((selection) => selection.highlightEntity);
    const clearHighlight = useSelectionStore((selection) => selection.clearHighlight);
    const setComparisonSample = useSelectionStore((selection) => selection.setComparisonSample);
    const morphFirst = useMorphStore((morph) => morph.first);
    const morphSecond = useMorphStore((morph) => morph.second);
    const weight = useMorphStore((morph) => morph.weight);
    const playOnRelease = useMorphStore((morph) => morph.playOnRelease);
    const join = useMorphStore((morph) => morph.join);
    const setWeight = useMorphStore((morph) => morph.setWeight);
    const { play } = useAudioPreview();
    const morphStatus = useMorphStatus();
    const link = useMemo(
        (): CloudLink | null =>
            morphFirst !== null && morphSecond !== null ? { first: morphFirst, second: morphSecond, weight } : null,
        [morphFirst, morphSecond, weight],
    );
    const morphAnchor = highlighted?.kind === "sample" ? highlighted.hash : focusedSampleHash;
    const rateByHash = useMemo(() => {
        const rates = new Map<string, number>();
        if (state.status === "success") {
            for (const point of state.data) {
                if (point.playbackRateHz !== undefined) {
                    rates.set(point.ref.hash, point.playbackRateHz);
                }
            }
        }
        return rates;
    }, [state]);

    useEffect(() => {
        setHovered(null);
    }, [tab]);

    function handleSelect(entity: EntityRef): void {
        highlightEntity(entity);
    }

    function handleActivate(entity: EntityRef): void {
        if (entity.kind === "sample") {
            play(samplePreview(entity.hash, rateByHash.get(entity.hash) ?? null));
        }
    }

    function handleFocus(entity: EntityRef): void {
        void navigate(entityRoute(entity));
    }

    function handleCompare(entity: EntityRef): void {
        if (entity.kind === "sample") {
            setComparisonSample(entity.hash);
            join(morphAnchor, entity.hash);
        }
    }

    function handleJoin(first: EntityRef, second: EntityRef): void {
        if (first.kind === "sample" && second.kind === "sample") {
            setComparisonSample(second.hash);
            join(first.hash, second.hash);
        }
    }

    function handleWeightCommit(): void {
        if (playOnRelease && link !== null && morphStatus.available) {
            play(morphPreview(link.first, link.second, link.weight));
        }
    }

    function handleHover(entity: EntityRef | null, screenPosition: readonly [number, number] | null): void {
        setHovered(
            entity !== null && screenPosition !== null ? { entity, x: screenPosition[0], y: screenPosition[1] } : null,
        );
    }

    return (
        <div className="panel-stack">
            <div className="panel-filter">
                <button
                    type="button"
                    aria-pressed={tab === "samples"}
                    onClick={() => {
                        setTab("samples");
                    }}
                >
                    Samples
                </button>
                <button
                    type="button"
                    aria-pressed={tab === "modules"}
                    onClick={() => {
                        setTab("modules");
                    }}
                >
                    Modules
                </button>
                {tab === "samples" && (
                    <>
                        <span className="panel-filter-separator" aria-hidden />
                        <span className="panel-filter-caption">Color by</span>
                        <button
                            type="button"
                            aria-pressed={mode === "category"}
                            onClick={() => {
                                setMode("category");
                            }}
                        >
                            Category
                        </button>
                        <button
                            type="button"
                            aria-pressed={mode === "label"}
                            onClick={() => {
                                setMode("label");
                            }}
                        >
                            Labels
                        </button>
                        <button
                            type="button"
                            aria-pressed={mode === "suggestion"}
                            onClick={() => {
                                setMode("suggestion");
                            }}
                        >
                            Suggestions
                        </button>
                    </>
                )}
            </div>
            {tab === "modules" && <p className="cloud-caption">{MODULE_TAB_CAPTION}</p>}
            {tab === "samples" && mode !== "category" && (
                <TagLegend tags={tags} painted={painted} onToggle={togglePainted} />
            )}
            <div className="panel-body cloud-body">
                {state.status === "loading" && <Loading />}
                {state.status === "error" && <ErrorNotice message={state.message} />}
                {state.status === "success" && (
                    <>
                        <CloudView
                            points={state.data}
                            coloring={coloring}
                            highlighted={highlighted}
                            onSelect={handleSelect}
                            onFocus={handleFocus}
                            onClear={clearHighlight}
                            onHover={handleHover}
                            onCompare={handleCompare}
                            onJoin={handleJoin}
                            onActivate={handleActivate}
                            link={tab === "samples" ? link : null}
                            onWeightChange={setWeight}
                            onWeightCommit={handleWeightCommit}
                            anchor={tab === "samples" ? morphAnchor : null}
                        />
                        {hovered !== null && <CloudHoverTooltip entity={hovered.entity} x={hovered.x} y={hovered.y} />}
                    </>
                )}
            </div>
        </div>
    );
}
