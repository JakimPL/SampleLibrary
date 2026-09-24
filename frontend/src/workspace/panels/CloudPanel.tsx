import { type ReactElement, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { CloudCategory, CloudLabel, CloudPoint, ModuleCloudPoint } from "../../api/cloud";
import { type CloudAction, type CloudCommand, type CloudLink, CloudView } from "../../cloud/CloudView";
import { type ColoringMode, ColoringModeChoice } from "../../cloud/ColoringModeChoice";
import type { CloudEntityPoint } from "../../cloud/geometry";
import {
    defaultPaintedTags,
    labelColoring,
    type PointColoring,
    SUBSTRATE_ONLY_COLORING,
    type TopLevelTag,
    topLevelTags,
} from "../../cloud/labelColoring";
import { LegendSheet } from "../../cloud/LegendSheet";
import { TagLegend } from "../../cloud/TagLegend";
import { useCategoryTags } from "../../cloud/useCategoryTags";
import { useCloud } from "../../cloud/useCloud";
import { useCloudCategories } from "../../cloud/useCloudCategories";
import { useCloudLabels } from "../../cloud/useCloudLabels";
import { useModuleCloud } from "../../cloud/useModuleCloud";
import { useContainerWidth } from "../../layout/useContainerWidth";
import { useLayoutMode } from "../../layout/useLayoutMode";
import { useMorphStore } from "../../morph/morphStore";
import { MorphStrip } from "../../morph/MorphStrip";
import { useMorphPlayback } from "../../morph/useMorphPlayback";
import { samplePreview, useAudioPreview } from "../../samples/useAudioPreview";
import { useLabelTags } from "../../samples/useLabelTags";
import { ErrorNotice } from "../../shared/ErrorNotice";
import type { FetchState } from "../../shared/fetchState";
import { Icon } from "../../shared/icons/Icon";
import { Loading } from "../../shared/Loading";
import { type EntityRef, morphAnchorOf, useSelectionStore } from "../selectionStore";
import { entityRoute } from "../useEntityRowInteractions";
import { CloudHoverTooltip } from "./CloudHoverTooltip";
import { CloudPointMenu } from "./CloudPointMenu";
import { CloudTapCard } from "./CloudTapCard";

type CloudTab = "samples" | "modules";

const NO_TAGS: readonly TopLevelTag[] = [];
const EMPTY_CAPTIONS: Readonly<Record<ColoringMode, string>> = {
    category: "No sample carries a category yet. A scoring of the listening model writes them.",
    label: "No sample carries a label yet. Labels written in a sample's detail panel appear here.",
};

interface HoveredPoint {
    readonly entity: EntityRef;
    readonly x: number;
    readonly y: number;
}

/** Below this panel width the legend leaves its row for a sheet. */
const LEGEND_SHEET_WIDTH_PX = 480;
const ZOOM_STEP_FACTOR = 1.5;

interface HeldPoint {
    readonly entity: EntityRef;
}

function samplePoints(coordinates: readonly CloudPoint[]): readonly CloudEntityPoint[] {
    return coordinates.map((coordinate) => ({
        ref: { kind: "sample", hash: coordinate.sample_hash },
        x: coordinate.x,
        y: coordinate.y,
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

/** A sample's top category in the shape the label coloring paints by: one path, the way a written label's first tag is. */
function categoriesAsLabels(categories: readonly CloudCategory[]): readonly CloudLabel[] {
    return categories.map((category) => ({ sample_hash: category.sample_hash, paths: [category.path] }));
}

/**
 * How the sample points are colored. The category mode paints each sample by the tag the listening
 * model heard first, its legend drawn from the scoring's vocabulary, so a point wears the color its
 * badge does. The label mode paints the same way from the tags a person wrote. In either, the
 * painted tags are a person's own choice once they touch the legend, and the most used ones until
 * then -- so a vocabulary that grows during a labeling session keeps showing whatever was chosen,
 * and a fresh session shows the tags with the most to show; a chosen set belongs to one mode, so
 * switching starts the other from its own most-used tags. A mode's sources are fetched the first
 * time it is chosen and kept for the session, and until they land every point waits on the ground.
 */
function useSampleColoring(mode: ColoringMode): {
    readonly coloring: PointColoring;
    readonly tags: readonly TopLevelTag[];
    readonly painted: readonly string[];
    readonly togglePainted: (name: string) => void;
} {
    const labelsState = useCloudLabels(mode === "label");
    const tagsState = useLabelTags(mode === "label");
    const categoriesState = useCloudCategories(mode === "category");
    const categoryTagsState = useCategoryTags(mode === "category");
    const [chosen, setChosen] = useState<readonly string[] | null>(null);
    useEffect(() => {
        setChosen(null);
    }, [mode]);
    const tags = useMemo(() => {
        const source = mode === "category" ? categoryTagsState : tagsState;
        return source.status === "success" ? topLevelTags(source.data) : NO_TAGS;
    }, [mode, tagsState, categoryTagsState]);
    const painted = useMemo(() => chosen ?? defaultPaintedTags(tags), [chosen, tags]);
    const coloring = useMemo((): PointColoring => {
        if (mode === "label" && labelsState.status === "success") {
            return labelColoring(labelsState.data, tags, painted);
        }
        if (mode === "category" && categoriesState.status === "success") {
            return labelColoring(categoriesAsLabels(categoriesState.data), tags, painted);
        }
        return SUBSTRATE_ONLY_COLORING;
    }, [mode, labelsState, categoriesState, tags, painted]);

    function togglePainted(name: string): void {
        setChosen(painted.includes(name) ? painted.filter((candidate) => candidate !== name) : [...painted, name]);
    }

    return { coloring, tags, painted, togglePainted };
}

/**
 * The cloud with its controls: the tab and the coloring, with the legend as a row, or, when the
 * panel is narrow, the coloring and the legend together in a sheet behind one Legend button, and
 * the tools that move the view. Under touch a tapped point shows a card
 * in place of the hover tooltip, except on a phone, where the tray names it; a held point opens
 * its menu. The strip along the bottom holds the morph's two ends: a selected end takes every
 * tapped point, and the slider and the waveform open under the row once the pair is whole.
 */
export function CloudPanel(): ReactElement {
    const [tab, setTab] = useState<CloudTab>("samples");
    const [mode, setMode] = useState<ColoringMode>("category");
    const [hovered, setHovered] = useState<HoveredPoint | null>(null);
    const [held, setHeld] = useState<HeldPoint | null>(null);
    const [legendOpen, setLegendOpen] = useState(false);
    const [command, setCommand] = useState<CloudCommand | null>(null);
    const panelRef = useRef<HTMLDivElement | null>(null);
    const width = useContainerWidth(panelRef);
    const legendAsSheet = width !== null && width < LEGEND_SHEET_WIDTH_PX;
    const { input, layout } = useLayoutMode();
    const state = useActiveCloudPoints(tab);
    const { coloring, tags, painted, togglePainted } = useSampleColoring(mode);
    const navigate = useNavigate();
    const highlighted = useSelectionStore((selection) => selection.highlighted);
    const morphAnchor = useSelectionStore(morphAnchorOf);
    const highlightEntity = useSelectionStore((selection) => selection.highlightEntity);
    const clearHighlight = useSelectionStore((selection) => selection.clearHighlight);
    const morphFirst = useMorphStore((morph) => morph.first);
    const morphSecond = useMorphStore((morph) => morph.second);
    const weight = useMorphStore((morph) => morph.weight);
    const join = useMorphStore((morph) => morph.join);
    const takeSample = useMorphStore((morph) => morph.takeSample);
    const setWeight = useMorphStore((morph) => morph.setWeight);
    const { play } = useAudioPreview();
    const playback = useMorphPlayback();
    const link = useMemo(
        (): CloudLink | null =>
            morphFirst !== null && morphSecond !== null ? { first: morphFirst, second: morphSecond, weight } : null,
        [morphFirst, morphSecond, weight],
    );
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
    const hashesInView = useMemo(
        () => new Set(state.status === "success" ? state.data.map((point) => point.ref.hash) : []),
        [state],
    );
    const inHandHere = highlighted !== null && hashesInView.has(highlighted.hash) ? highlighted : null;
    const tapCardShown = input === "touch" && layout === "workspace" && inHandHere !== null;

    useEffect(() => {
        setHovered(null);
        setHeld(null);
    }, [tab]);

    function issue(action: CloudAction): void {
        setCommand((current) => ({ sequence: (current?.sequence ?? 0) + 1, action }));
    }

    function handleContextMenu(entity: EntityRef): void {
        setHeld({ entity });
    }

    function handleLocate(hash: string): void {
        issue({ kind: "locate", hash });
    }

    function handleSelect(entity: EntityRef): void {
        highlightEntity(entity);
        if (entity.kind === "sample") {
            takeSample(entity.hash);
        }
    }

    function handleActivate(entity: EntityRef): void {
        if (entity.kind === "sample") {
            play(samplePreview(entity.hash, rateByHash.get(entity.hash) ?? null));
        }
    }

    function handleFocus(entity: EntityRef): void {
        void navigate(entityRoute(entity));
    }

    function handleJoinToAnchor(entity: EntityRef): void {
        if (entity.kind === "sample") {
            join(morphAnchor, entity.hash);
        }
    }

    function handleJoin(first: EntityRef, second: EntityRef): void {
        if (first.kind === "sample" && second.kind === "sample") {
            join(first.hash, second.hash);
        }
    }

    function handleHover(entity: EntityRef | null, screenPosition: readonly [number, number] | null): void {
        setHovered(
            entity !== null && screenPosition !== null ? { entity, x: screenPosition[0], y: screenPosition[1] } : null,
        );
    }

    return (
        <div className="panel-stack" ref={panelRef}>
            <div className="panel-filter cloud-toolbar">
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
                        {legendAsSheet ? (
                            <button
                                type="button"
                                aria-expanded={legendOpen}
                                onClick={() => {
                                    setLegendOpen(true);
                                }}
                            >
                                Legend
                            </button>
                        ) : (
                            <>
                                <span className="panel-filter-caption">Color by</span>
                                <ColoringModeChoice mode={mode} onModeChange={setMode} />
                            </>
                        )}
                    </>
                )}
            </div>
            {tab === "samples" && !legendAsSheet && (
                <TagLegend tags={tags} painted={painted} onToggle={togglePainted} emptyCaption={EMPTY_CAPTIONS[mode]} />
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
                            onJoinToAnchor={handleJoinToAnchor}
                            onJoin={handleJoin}
                            onActivate={handleActivate}
                            onContextMenu={handleContextMenu}
                            command={command}
                            link={tab === "samples" ? link : null}
                            onWeightChange={setWeight}
                            onWeightCommit={playback.hearCurrentPoint}
                            anchor={tab === "samples" ? morphAnchor : null}
                        />
                        {hovered !== null && <CloudHoverTooltip entity={hovered.entity} x={hovered.x} y={hovered.y} />}
                        {tapCardShown && <CloudTapCard entity={inHandHere} />}
                        <div className="cloud-tools">
                            <button
                                type="button"
                                className="cloud-tool"
                                aria-label="Center on the selection"
                                disabled={inHandHere === null}
                                onClick={() => {
                                    if (inHandHere !== null) {
                                        handleLocate(inHandHere.hash);
                                    }
                                }}
                            >
                                ⌖
                            </button>
                            <button
                                type="button"
                                className="cloud-tool"
                                aria-label="Frame the pair"
                                disabled={link === null}
                                onClick={() => {
                                    if (link !== null) {
                                        issue({ kind: "frame", first: link.first, second: link.second });
                                    }
                                }}
                            >
                                <Icon name="morph" label={null} />
                            </button>
                            <button
                                type="button"
                                className="cloud-tool"
                                aria-label="Zoom in"
                                onClick={() => {
                                    issue({ kind: "zoom", factor: ZOOM_STEP_FACTOR });
                                }}
                            >
                                +
                            </button>
                            <button
                                type="button"
                                className="cloud-tool"
                                aria-label="Zoom out"
                                onClick={() => {
                                    issue({ kind: "zoom", factor: 1 / ZOOM_STEP_FACTOR });
                                }}
                            >
                                −
                            </button>
                        </div>
                    </>
                )}
            </div>
            {tab === "samples" && <MorphStrip />}
            {held !== null && (
                <CloudPointMenu
                    entity={held.entity}
                    playbackRateHz={rateByHash.get(held.entity.hash) ?? null}
                    onLocate={handleLocate}
                    onClose={() => {
                        setHeld(null);
                    }}
                />
            )}
            {legendOpen && (
                <LegendSheet
                    mode={mode}
                    onModeChange={setMode}
                    tags={tags}
                    painted={painted}
                    onToggle={togglePainted}
                    emptyCaption={EMPTY_CAPTIONS[mode]}
                    onClose={() => {
                        setLegendOpen(false);
                    }}
                />
            )}
        </div>
    );
}
