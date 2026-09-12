import type { KeyboardEvent, PointerEvent, ReactElement } from "react";
import { useRef } from "react";

import { snapWeight, WEIGHT_STEP } from "../morph/morphStore";
import { pointAlong, projectWeight, type ScreenPoint } from "./linkGeometry";

const END_RADIUS_PX = 6;

interface MorphLinkProps {
    readonly first: ScreenPoint;
    readonly second: ScreenPoint;
    readonly weight: number;
    readonly onWeightChange: (weight: number) => void;
    readonly onWeightCommit: () => void;
    readonly onDragChange: (dragging: boolean) => void;
}

function nudgedWeight(key: string, weight: number): number | null {
    switch (key) {
        case "ArrowLeft":
        case "ArrowDown":
            return snapWeight(weight - WEIGHT_STEP);
        case "ArrowRight":
        case "ArrowUp":
            return snapWeight(weight + WEIGHT_STEP);
        case "Home":
            return 0;
        case "End":
            return 1;
        default:
            return null;
    }
}

/**
 * The line joining a morph's two ends on the cloud, with the weight as a marker along it. The
 * marker is the one element here that takes pointer events, and it captures them while dragged,
 * so the scatterplot beneath never sees a drag it would read as a pan; the wrapper passes every
 * other pointer through to the points. Dragging reports the projected, snapped weight as it moves
 * and a commit on release; the keyboard nudges by one step and commits on key release, so a held
 * key plays once.
 */
export function MorphLink({
    first,
    second,
    weight,
    onWeightChange,
    onWeightCommit,
    onDragChange,
}: MorphLinkProps): ReactElement {
    const wrapperRef = useRef<HTMLDivElement | null>(null);
    const draggingRef = useRef(false);
    const [markerX, markerY] = pointAlong(first, second, weight);

    function weightAt(event: PointerEvent<HTMLDivElement>): number {
        const bounds = wrapperRef.current?.getBoundingClientRect();
        const point: ScreenPoint = [event.clientX - (bounds?.left ?? 0), event.clientY - (bounds?.top ?? 0)];
        return snapWeight(projectWeight(first, second, point));
    }

    function handlePointerDown(event: PointerEvent<HTMLDivElement>): void {
        event.currentTarget.setPointerCapture(event.pointerId);
        draggingRef.current = true;
        onDragChange(true);
    }

    function handlePointerMove(event: PointerEvent<HTMLDivElement>): void {
        if (draggingRef.current) {
            onWeightChange(weightAt(event));
        }
    }

    function handlePointerEnd(event: PointerEvent<HTMLDivElement>): void {
        if (!draggingRef.current) {
            return;
        }
        draggingRef.current = false;
        event.currentTarget.releasePointerCapture(event.pointerId);
        onDragChange(false);
        onWeightCommit();
    }

    function handleKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
        const nudged = nudgedWeight(event.key, weight);
        if (nudged !== null) {
            event.preventDefault();
            onWeightChange(nudged);
        }
    }

    function handleKeyUp(event: KeyboardEvent<HTMLDivElement>): void {
        if (nudgedWeight(event.key, weight) !== null) {
            onWeightCommit();
        }
    }

    return (
        <div className="morph-link" ref={wrapperRef}>
            <svg aria-hidden>
                <line className="morph-link-line" x1={first[0]} y1={first[1]} x2={second[0]} y2={second[1]} />
                <circle className="morph-link-end" cx={first[0]} cy={first[1]} r={END_RADIUS_PX} />
                <circle className="morph-link-end" cx={second[0]} cy={second[1]} r={END_RADIUS_PX} />
            </svg>
            <div
                role="slider"
                tabIndex={0}
                className="morph-link-marker"
                aria-label="Morph weight"
                aria-valuemin={0}
                aria-valuemax={1}
                aria-valuenow={weight}
                style={{ left: markerX, top: markerY }}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerEnd}
                onPointerCancel={handlePointerEnd}
                onKeyDown={handleKeyDown}
                onKeyUp={handleKeyUp}
            />
        </div>
    );
}
