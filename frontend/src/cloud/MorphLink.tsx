import type { KeyboardEvent, PointerEvent, ReactElement } from "react";
import { useRef, useState } from "react";

import { snapWeight, WEIGHT_STEP } from "../morph/morphStore";
import { classNames } from "../shared/classNames";
import { pointAlong, projectWeight, type ScreenPoint } from "./linkGeometry";
import { lineBetweenMarkers, type MarkerAppearance, snapToDevicePixel } from "./markerGeometry";
import { PointMarker } from "./PointMarker";

const SQUARE_SHAPE = "square";

interface MorphLinkProps {
    readonly first: ScreenPoint;
    readonly second: ScreenPoint;
    readonly weight: number;
    readonly appearance: MarkerAppearance;
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
 *
 * The ends are marked in the theme's point shape. Under round points the weight marker is the
 * round knob the stylesheet draws; under square points it is a square node framed on whole device
 * pixels, lit while dragged the way OpenMPT lights the envelope node under the mouse, and the line
 * keeps hard pixel edges to match.
 */
export function MorphLink({
    first,
    second,
    weight,
    appearance,
    onWeightChange,
    onWeightCommit,
    onDragChange,
}: MorphLinkProps): ReactElement {
    const wrapperRef = useRef<HTMLDivElement | null>(null);
    const draggingRef = useRef(false);
    const [dragging, setDragging] = useState(false);
    const [markerX, markerY] = pointAlong(first, second, weight);
    const line = lineBetweenMarkers(first, second, appearance, true);
    const square = appearance.shape === SQUARE_SHAPE;
    const knobLeft = square ? snapToDevicePixel(markerX, appearance.devicePixelRatio) : markerX;
    const knobTop = square ? snapToDevicePixel(markerY, appearance.devicePixelRatio) : markerY;

    function weightAt(event: PointerEvent<HTMLDivElement>): number {
        const bounds = wrapperRef.current?.getBoundingClientRect();
        const point: ScreenPoint = [event.clientX - (bounds?.left ?? 0), event.clientY - (bounds?.top ?? 0)];
        return snapWeight(projectWeight(first, second, point));
    }

    function changeDragging(next: boolean): void {
        draggingRef.current = next;
        setDragging(next);
        onDragChange(next);
    }

    function handlePointerDown(event: PointerEvent<HTMLDivElement>): void {
        event.currentTarget.setPointerCapture(event.pointerId);
        changeDragging(true);
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
        event.currentTarget.releasePointerCapture(event.pointerId);
        changeDragging(false);
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
                {line !== null && (
                    <>
                        <line
                            className="morph-link-casing"
                            x1={line[0][0]}
                            y1={line[0][1]}
                            x2={line[1][0]}
                            y2={line[1][1]}
                        />
                        <line
                            className="morph-link-line"
                            x1={line[0][0]}
                            y1={line[0][1]}
                            x2={line[1][0]}
                            y2={line[1][1]}
                            {...(square && { shapeRendering: "crispEdges" })}
                        />
                    </>
                )}
                <PointMarker className="morph-link-end" center={first} appearance={appearance} filled={false} />
                <PointMarker className="morph-link-end" center={second} appearance={appearance} filled={false} />
                {square && (
                    <PointMarker
                        className={classNames("morph-link-node", dragging && "morph-link-node-dragging")}
                        center={[knobLeft, knobTop]}
                        appearance={appearance}
                        filled
                    />
                )}
            </svg>
            <div
                role="slider"
                tabIndex={0}
                className={classNames("morph-link-marker", square && "morph-link-marker-square")}
                aria-label="Morph weight"
                aria-valuemin={0}
                aria-valuemax={1}
                aria-valuenow={weight}
                style={{ left: knobLeft, top: knobTop }}
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
