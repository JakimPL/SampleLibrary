import type { ReactElement, ReactNode } from "react";
import { useLayoutEffect, useRef, useState } from "react";

import { AT_RIGHT_ABOVE, placeTooltip, samePlacement, type TooltipPlacement } from "../../cloud/tooltipPlacement";
import { ModuleGlance } from "../../modules/ModuleGlance";
import { useModule } from "../../modules/useModule";
import { SampleGlance } from "../../samples/SampleGlance";
import { useSamplePreview } from "../../samples/useSamplePreview";
import { classNames } from "../../shared/classNames";
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

interface TooltipFrameProps {
    readonly x: number;
    readonly y: number;
    readonly children: ReactNode;
}

/**
 * The popup's frame at the point's screen position, turned to whichever side of the point keeps it
 * inside the cloud: it measures itself against its positioned parent before the frame paints, so a
 * point near the right edge or the top edge gets its popup on the left or below.
 */
function TooltipFrame({ x, y, children }: TooltipFrameProps): ReactElement {
    const frameRef = useRef<HTMLDivElement | null>(null);
    const [placement, setPlacement] = useState<TooltipPlacement>(AT_RIGHT_ABOVE);

    useLayoutEffect(() => {
        const frame = frameRef.current;
        const container = frame?.offsetParent;
        if (frame === null || !(container instanceof HTMLElement)) {
            return;
        }
        const next = placeTooltip(
            x,
            y,
            { widthPx: frame.offsetWidth, heightPx: frame.offsetHeight },
            { widthPx: container.clientWidth, heightPx: container.clientHeight },
        );
        setPlacement((current) => (samePlacement(current, next) ? current : next));
    }, [x, y]);

    return (
        <div
            ref={frameRef}
            className={classNames("cloud-hover-tooltip", placement.left && "is-left", placement.below && "is-below")}
            style={{ left: x, top: y }}
        >
            {children}
        </div>
    );
}

function SampleHoverTooltip({ hash, x, y }: EntityTooltipProps): ReactElement | null {
    const state = useSamplePreview(hash);
    if (state.status !== "success") {
        return null;
    }

    return (
        <TooltipFrame x={x} y={y}>
            <SampleGlance hash={hash} preview={state.data} />
        </TooltipFrame>
    );
}

function ModuleHoverTooltip({ hash, x, y }: EntityTooltipProps): ReactElement | null {
    const state = useModule(hash);
    if (state.status !== "success") {
        return null;
    }

    return (
        <TooltipFrame x={x} y={y}>
            <ModuleGlance hash={hash} module={state.data} />
        </TooltipFrame>
    );
}

/**
 * A minimal popup for whichever point the cursor is currently over: the entity at a glance, its
 * name, a short git-style abbreviated hash as a stable identity even for an unnamed sample, and
 * for a sample its compact waveform. Positioned at the point's own screen coordinates, which
 * `CloudView` reports through its `onHover` callback, on the side of the point that keeps it in view.
 */
export function CloudHoverTooltip({ entity, x, y }: CloudHoverTooltipProps): ReactElement | null {
    return entity.kind === "sample" ? (
        <SampleHoverTooltip hash={entity.hash} x={x} y={y} />
    ) : (
        <ModuleHoverTooltip hash={entity.hash} x={x} y={y} />
    );
}
