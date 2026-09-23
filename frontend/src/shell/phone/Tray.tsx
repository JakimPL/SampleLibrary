import type { ReactElement, ReactNode } from "react";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";

import { NO_DECISIONS } from "../../api/curation";
import { ModuleGlance } from "../../modules/ModuleGlance";
import { useModule } from "../../modules/useModule";
import { defaultScopeFor } from "../../samples/AnnotationEditor";
import { decisionsOf, useSampleAnnotation } from "../../samples/annotationStore";
import { CategoryBadge } from "../../samples/CategoryBadge";
import { FavoriteToggle } from "../../samples/FavoriteToggle";
import { MiniWaveform } from "../../samples/MiniWaveform";
import { RatingStars } from "../../samples/RatingStars";
import { useAnnotationWriter } from "../../samples/useAnnotationWriter";
import { samplePreview, useAudioPreview } from "../../samples/useAudioPreview";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { useSamplePreview } from "../../samples/useSamplePreview";
import { classNames } from "../../shared/classNames";
import { shortHash } from "../../shared/format";
import { useDoubleTap } from "../../shared/gestures/useDoubleTap";
import { Icon } from "../../shared/icons/Icon";
import { UNNAMED_SAMPLE_LABEL } from "../../shared/labels";
import { OptionalLabel } from "../../shared/OptionalLabel";
import { type EntityRef, useSelectionStore } from "../../workspace/selectionStore";
import { entityRoute } from "../../workspace/useEntityRowInteractions";

const SMALLEST_GROUP = 1;

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

interface TrayIdentityProps {
    readonly entity: EntityRef;
    readonly children: ReactNode;
}

/** The tray's name column, which a double tap opens as a page, as › does. */
function TrayIdentity({ entity, children }: TrayIdentityProps): ReactElement {
    const navigate = useNavigate();
    const { onClick } = useDoubleTap(() => {
        void navigate(entityRoute(entity));
    });

    return (
        <button type="button" className="tray-identity" onClick={onClick}>
            {children}
        </button>
    );
}

function SampleTray({ hash }: EntityTrayProps): ReactElement {
    const preview = useSamplePreview(hash);
    const detail = useSampleDetail(hash);
    const sample = detail.status === "success" ? detail.data.sample : null;
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
                <TrayIdentity entity={{ kind: "sample", hash }}>
                    <span className="tray-name">
                        {name === null ? (
                            <span className="mono">{shortHash(hash)}</span>
                        ) : (
                            <OptionalLabel value={name} placeholder={UNNAMED_SAMPLE_LABEL} />
                        )}
                    </span>
                    <span className="entity-hash tray-meta mono">
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
                </TrayIdentity>
                {sample !== null && (
                    <>
                        <RatingStars
                            rating={decisions.rating}
                            onRatingChange={(rating) => {
                                change({ rating });
                            }}
                        />
                        <FavoriteToggle
                            favorite={decisions.favorite}
                            onFavoriteChange={(favorite) => {
                                change({ favorite });
                            }}
                        />
                    </>
                )}
                {message !== null && (
                    <span className="annotation-row-message" role="alert" title={message}>
                        Not saved
                    </span>
                )}
                <Link to={entityRoute({ kind: "sample", hash })} className="tray-open" aria-label="Open sample">
                    ›
                </Link>
            </div>
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
                <TrayIdentity entity={{ kind: "module", hash }}>
                    {state.status === "success" ? (
                        <ModuleGlance hash={hash} module={state.data} />
                    ) : (
                        <span className="tray-name mono">{shortHash(hash)}</span>
                    )}
                </TrayIdentity>
                <Link to={entityRoute({ kind: "module", hash })} className="tray-open" aria-label="Open module">
                    ›
                </Link>
            </div>
        </div>
    );
}

interface TrayProps {
    /** What the tray says while nothing is in hand, or `null` to take no room then. */
    readonly idleHint: string | null;
}

/**
 * The strip above the tabs naming the entity in hand, where the highlight a row or a cloud point
 * gets becomes something to act on, all on one row: a sample plays and pauses from its thumbnail,
 * takes its stars and its heart, and opens from › or from a double tap on its name; a module names
 * itself and opens the same two ways. The label is written on the sample's page or from a held
 * row. With nothing in hand the strip shows
 * `idleHint`, or takes no room at all: the cloud keeps its slot, so a tap that fills the tray
 * leaves the points where they were.
 */
export function Tray({ idleHint }: TrayProps): ReactElement | null {
    const entity = useEntityInHand();
    if (entity === null) {
        return idleHint === null ? null : <div className="tray tray-hint">{idleHint}</div>;
    }
    return entity.kind === "sample" ? (
        <SampleTray key={entity.hash} hash={entity.hash} />
    ) : (
        <ModuleTray key={entity.hash} hash={entity.hash} />
    );
}
