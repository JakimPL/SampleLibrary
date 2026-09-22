import type { ReactElement } from "react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { NO_DECISIONS } from "../../api/curation";
import { ModuleGlance } from "../../modules/ModuleGlance";
import { useModule } from "../../modules/useModule";
import { defaultScopeFor } from "../../samples/AnnotationEditor";
import { decisionsOf, useSampleAnnotation } from "../../samples/annotationStore";
import { CategoryBadge } from "../../samples/CategoryBadge";
import { FavoriteToggle } from "../../samples/FavoriteToggle";
import { LabelSheet } from "../../samples/LabelSheet";
import { MiniWaveform } from "../../samples/MiniWaveform";
import { RatingStars } from "../../samples/RatingStars";
import { SampleActions } from "../../samples/SampleActions";
import { useAnnotationWriter } from "../../samples/useAnnotationWriter";
import { samplePreview, useAudioPreview } from "../../samples/useAudioPreview";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { useSamplePreview } from "../../samples/useSamplePreview";
import { classNames } from "../../shared/classNames";
import { shortHash } from "../../shared/format";
import { Icon } from "../../shared/icons/Icon";
import { UNNAMED_SAMPLE_LABEL } from "../../shared/labels";
import { OptionalLabel } from "../../shared/OptionalLabel";
import { type EntityRef, useSelectionStore } from "../../workspace/selectionStore";
import { entityRoute } from "../../workspace/useEntityRowInteractions";
import { usePhoneShellStore } from "./phoneShellStore";

const SMALLEST_GROUP = 1;
const LABEL_PLACEHOLDER = "Label…";

interface EntityTrayProps {
    readonly hash: string;
}

/**
 * The entity in hand: the one highlighted anywhere in the shell, and the focused sample while
 * nothing is highlighted, so the tray names what a tap or an address last put in front.
 */
export function useEntityInHand(): EntityRef | null {
    const highlighted = useSelectionStore((state) => state.highlighted);
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);
    return useMemo(
        () => highlighted ?? (focusedSampleHash === null ? null : { kind: "sample", hash: focusedSampleHash }),
        [highlighted, focusedSampleHash],
    );
}

function SampleTray({ hash }: EntityTrayProps): ReactElement {
    const preview = useSamplePreview(hash);
    const detail = useSampleDetail(hash);
    const sample = detail.status === "success" ? detail.data.sample : null;
    const expanded = usePhoneShellStore((state) => state.trayExpanded);
    const setExpanded = usePhoneShellStore((state) => state.setTrayExpanded);
    const [labelOpen, setLabelOpen] = useState(false);
    const { play, pause, resume, playingKey, paused, source } = useAudioPreview();
    const decisions = useSampleAnnotation(hash, sample === null ? NO_DECISIONS : decisionsOf(sample)) ?? NO_DECISIONS;
    const { change, message } = useAnnotationWriter(hash, sample === null ? "sample" : defaultScopeFor(sample));
    const isSounding = playingKey === hash;
    const name = preview.status === "success" ? preview.data.display_name : (sample?.display_name ?? null);

    function handlePlay(): void {
        if (isSounding) {
            if (paused) {
                resume();
            } else {
                pause();
            }
            return;
        }
        play(source?.key === hash ? source : samplePreview(hash, sample?.playback_rate_hz ?? null));
    }

    return (
        <div className="tray" role="region" aria-label="Sample in hand">
            <div className="tray-row">
                <button
                    type="button"
                    className={classNames("tray-play", isSounding && !paused && "is-playing")}
                    aria-label={isSounding && !paused ? "Pause sample" : "Play sample"}
                    aria-pressed={isSounding && !paused}
                    onClick={handlePlay}
                >
                    {preview.status === "success" && preview.data.thumbnail !== null ? (
                        <MiniWaveform peaks={preview.data.thumbnail} />
                    ) : (
                        <span aria-hidden>▶</span>
                    )}
                </button>
                <button
                    type="button"
                    className="tray-identity"
                    aria-expanded={expanded}
                    onClick={() => {
                        setExpanded(!expanded);
                    }}
                >
                    <span className="tray-name">
                        {name === null ? (
                            <span className="mono">{shortHash(hash)}</span>
                        ) : (
                            <OptionalLabel value={name} placeholder={UNNAMED_SAMPLE_LABEL} />
                        )}
                    </span>
                    <span className="entity-hash mono">
                        {shortHash(hash)}
                        {sample !== null && sample.equivalence_member_count > SMALLEST_GROUP && (
                            <span className="badge badge-equivalence">×{sample.equivalence_member_count}</span>
                        )}
                        {preview.status === "success" && (
                            <CategoryBadge
                                sampleHash={hash}
                                category={preview.data.category}
                                handLabel={preview.data.hand_label}
                            />
                        )}
                    </span>
                </button>
                {sample !== null && (
                    <FavoriteToggle
                        favorite={decisions.favorite}
                        onFavoriteChange={(favorite) => {
                            change({ favorite });
                        }}
                    />
                )}
                <Link to={entityRoute({ kind: "sample", hash })} className="tray-open" aria-label="Open sample">
                    ›
                </Link>
            </div>
            {expanded && sample !== null && (
                <div className="tray-expanded">
                    <RatingStars
                        rating={decisions.rating}
                        onRatingChange={(rating) => {
                            change({ rating });
                        }}
                    />
                    <button
                        type="button"
                        className="tray-label"
                        onClick={() => {
                            setLabelOpen(true);
                        }}
                    >
                        {decisions.label ?? LABEL_PLACEHOLDER}
                    </button>
                    <SampleActions sampleHash={hash} playbackRateHz={sample.playback_rate_hz} />
                    {message !== null && (
                        <span className="annotation-row-message" role="alert" title={message}>
                            Not saved
                        </span>
                    )}
                </div>
            )}
            {labelOpen && (
                <LabelSheet
                    label={decisions.label}
                    onCommit={(label) => {
                        change({ label });
                    }}
                    onClose={() => {
                        setLabelOpen(false);
                    }}
                />
            )}
        </div>
    );
}

function ModuleTray({ hash }: EntityTrayProps): ReactElement {
    const state = useModule(hash);

    return (
        <div className="tray" role="region" aria-label="Module in hand">
            <div className="tray-row">
                <span className="tray-glyph">
                    <Icon name="modules" label={null} />
                </span>
                <div className="tray-identity">
                    {state.status === "success" ? (
                        <ModuleGlance hash={hash} module={state.data} />
                    ) : (
                        <span className="tray-name mono">{shortHash(hash)}</span>
                    )}
                </div>
                <Link to={entityRoute({ kind: "module", hash })} className="tray-open" aria-label="Open module">
                    ›
                </Link>
            </div>
        </div>
    );
}

/**
 * The strip above the tabs naming the entity in hand, where the highlight a row or a cloud point
 * gets becomes something to act on: a sample plays, pauses and opens from here, its heart is one
 * tap, and opened out it offers the stars, the label sheet and either end of the morph pair; a
 * module names itself and opens. Nothing in hand, nothing shown.
 */
export function Tray(): ReactElement | null {
    const entity = useEntityInHand();
    if (entity === null) {
        return null;
    }
    return entity.kind === "sample" ? (
        <SampleTray key={entity.hash} hash={entity.hash} />
    ) : (
        <ModuleTray key={entity.hash} hash={entity.hash} />
    );
}
