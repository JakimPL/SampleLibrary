import type { ReactElement } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { AnnotationChanges, AnnotationDecisions } from "../api/curation";
import type { SampleSummary } from "../api/samples";
import { useMorphStore } from "../morph/morphStore";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { ActionSheet, type SheetAction } from "../shared/overlay/ActionSheet";
import { entityRoute } from "../workspace/useEntityRowInteractions";
import { FavoriteToggle } from "./FavoriteToggle";
import { LabelSheet } from "./LabelSheet";
import { RatingStars } from "./RatingStars";
import { samplePreview, useAudioPreview } from "./useAudioPreview";

interface RowActionSheetProps {
    readonly sample: SampleSummary;
    readonly decisions: AnnotationDecisions;
    readonly onChange: (changes: AnnotationChanges) => void;
    readonly onClose: () => void;
}

/**
 * Everything a held sample row offers a finger: the stars and the heart at a tap's size, then
 * play, open, either end of the morph pair, the label, and the hash for the clipboard. It stands
 * in for the inline editors and the modifier clicks a row answers to under a pointer.
 */
export function RowActionSheet({ sample, decisions, onChange, onClose }: RowActionSheetProps): ReactElement {
    const [editingLabel, setEditingLabel] = useState(false);
    const navigate = useNavigate();
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const setFirst = useMorphStore((state) => state.setFirst);
    const setSecond = useMorphStore((state) => state.setSecond);
    const { play } = useAudioPreview();
    const title = sample.display_name.trim() === "" ? UNNAMED_SAMPLE_LABEL : sample.display_name;

    if (editingLabel) {
        return (
            <LabelSheet
                label={decisions.label}
                onCommit={(label) => {
                    onChange({ label });
                }}
                onClose={onClose}
            />
        );
    }

    const actions: readonly SheetAction[] = [
        {
            id: "play",
            label: "Play",
            disabled: false,
            run: () => {
                play(samplePreview(sample.hash, sample.playback_rate_hz));
            },
        },
        {
            id: "open",
            label: "Open",
            disabled: false,
            run: () => {
                void navigate(entityRoute({ kind: "sample", hash: sample.hash }));
            },
        },
        {
            id: "morph-from",
            label: first === sample.hash ? "This is A" : "Morph from here",
            disabled: first === sample.hash,
            run: () => {
                setFirst(sample.hash);
            },
        },
        {
            id: "morph-to",
            label: second === sample.hash ? "This is B" : "Morph to here",
            disabled: second === sample.hash,
            run: () => {
                setSecond(sample.hash);
            },
        },
        {
            id: "copy-hash",
            label: "Copy hash",
            disabled: false,
            run: () => {
                void navigator.clipboard.writeText(sample.hash).catch(() => undefined);
            },
        },
    ];

    return (
        <ActionSheet title={title} actions={actions} onClose={onClose}>
            <div className="sheet-verdict">
                <RatingStars
                    rating={decisions.rating}
                    onRatingChange={(rating) => {
                        onChange({ rating });
                    }}
                />
                <FavoriteToggle
                    favorite={decisions.favorite}
                    onFavoriteChange={(favorite) => {
                        onChange({ favorite });
                    }}
                />
            </div>
            <div className="sheet-actions">
                <button
                    type="button"
                    onClick={() => {
                        setEditingLabel(true);
                    }}
                >
                    Label…
                </button>
            </div>
        </ActionSheet>
    );
}
