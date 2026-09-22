import type { ReactElement } from "react";

import { ModuleGlance } from "../../modules/ModuleGlance";
import { useModule } from "../../modules/useModule";
import { SampleGlance } from "../../samples/SampleGlance";
import { useSamplePreview } from "../../samples/useSamplePreview";
import type { EntityRef } from "../selectionStore";

interface CloudHoverTooltipProps {
    readonly entity: EntityRef;
    readonly x: number;
    readonly y: number;
}

interface EntityTooltipProps {
    readonly hash: string;
    readonly x: number;
    readonly y: number;
}

function SampleHoverTooltip({ hash, x, y }: EntityTooltipProps): ReactElement | null {
    const state = useSamplePreview(hash);
    if (state.status !== "success") {
        return null;
    }

    return (
        <div className="cloud-hover-tooltip" style={{ left: x, top: y }}>
            <SampleGlance hash={hash} preview={state.data} />
        </div>
    );
}

function ModuleHoverTooltip({ hash, x, y }: EntityTooltipProps): ReactElement | null {
    const state = useModule(hash);
    if (state.status !== "success") {
        return null;
    }

    return (
        <div className="cloud-hover-tooltip" style={{ left: x, top: y }}>
            <ModuleGlance hash={hash} module={state.data} />
        </div>
    );
}

/**
 * A minimal popup for whichever point the cursor is currently over: the entity at a glance, its
 * name, a short git-style abbreviated hash as a stable identity even for an unnamed sample, and
 * for a sample its compact waveform. Positioned at the point's own screen coordinates, which
 * `CloudView` reports through its `onHover` callback.
 */
export function CloudHoverTooltip({ entity, x, y }: CloudHoverTooltipProps): ReactElement | null {
    return entity.kind === "sample" ? (
        <SampleHoverTooltip hash={entity.hash} x={x} y={y} />
    ) : (
        <ModuleHoverTooltip hash={entity.hash} x={x} y={y} />
    );
}
