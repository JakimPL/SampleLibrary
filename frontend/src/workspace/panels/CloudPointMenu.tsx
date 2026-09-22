import type { ReactElement } from "react";
import { useNavigate } from "react-router-dom";

import { samplePreview, useAudioPreview } from "../../samples/useAudioPreview";
import { shortHash } from "../../shared/format";
import { ActionSheet, type SheetAction } from "../../shared/overlay/ActionSheet";
import type { EntityRef } from "../selectionStore";
import { entityRoute } from "../useEntityRowInteractions";

interface CloudPointMenuProps {
    readonly entity: EntityRef;
    readonly playbackRateHz: number | null;
    /** Brings the point to the middle of the view. */
    readonly onLocate: (hash: string) => void;
    readonly onClose: () => void;
}

/**
 * What a finger held on a point can do with it: play a sample, open either kind, and bring the
 * point to the middle of the view.
 */
export function CloudPointMenu({ entity, playbackRateHz, onLocate, onClose }: CloudPointMenuProps): ReactElement {
    const navigate = useNavigate();
    const { play } = useAudioPreview();

    const sampleActions: readonly SheetAction[] =
        entity.kind === "sample"
            ? [
                  {
                      id: "play",
                      label: "Play",
                      disabled: false,
                      run: () => {
                          play(samplePreview(entity.hash, playbackRateHz));
                      },
                  },
              ]
            : [];
    const actions: readonly SheetAction[] = [
        ...sampleActions,
        {
            id: "open",
            label: "Open",
            disabled: false,
            run: () => {
                void navigate(entityRoute(entity));
            },
        },
        {
            id: "locate",
            label: "Center on this point",
            disabled: false,
            run: () => {
                onLocate(entity.hash);
            },
        },
    ];

    return (
        <ActionSheet
            title={`${entity.kind === "sample" ? "Sample" : "Module"} ${shortHash(entity.hash)}`}
            actions={actions}
            onClose={onClose}
        >
            {null}
        </ActionSheet>
    );
}
