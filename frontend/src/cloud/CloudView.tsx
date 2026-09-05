import type { MouseEvent, ReactElement } from "react";
import { useEffect, useMemo, useRef } from "react";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";

import type { CloudPoint } from "../api/cloud";
import { findNearestPoint, type NormalizedPoint, normalizePoints } from "./geometry";

const CANVAS_SIZE = 800;
const POINT_RADIUS = 3;
const HIGHLIGHT_RADIUS = 6;
const HIT_TEST_RADIUS = 0.02;
// eslint-disable-next-line @typescript-eslint/no-magic-numbers -- 2π reads clearer as a literal multiplication than a precomputed constant
const FULL_CIRCLE_RADIANS = 2 * Math.PI;

interface CloudViewProps {
    readonly points: readonly CloudPoint[];
    readonly highlightedSampleHash: string | null;
    readonly onSelect: (sampleHash: string) => void;
    readonly onFocus: (sampleHash: string) => void;
}

function drawPoint(context: CanvasRenderingContext2D, point: NormalizedPoint, radius: number): void {
    context.beginPath();
    context.arc(point.x * CANVAS_SIZE, point.y * CANVAS_SIZE, radius, 0, FULL_CIRCLE_RADIANS);
    context.fill();
}

export function CloudView({
    points: rawPoints,
    highlightedSampleHash,
    onSelect,
    onFocus,
}: CloudViewProps): ReactElement {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const points = useMemo(() => normalizePoints(rawPoints), [rawPoints]);

    useEffect(() => {
        const context = canvasRef.current?.getContext("2d");
        if (!context) {
            return;
        }

        context.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
        context.fillStyle = "currentColor";
        for (const point of points) {
            drawPoint(context, point, POINT_RADIUS);
        }

        const highlighted = points.find((point) => point.sampleHash === highlightedSampleHash);
        if (highlighted) {
            context.strokeStyle = "currentColor";
            context.lineWidth = 2;
            context.beginPath();
            context.arc(
                highlighted.x * CANVAS_SIZE,
                highlighted.y * CANVAS_SIZE,
                HIGHLIGHT_RADIUS,
                0,
                FULL_CIRCLE_RADIANS,
            );
            context.stroke();
        }
    }, [points, highlightedSampleHash]);

    function hitTest(event: MouseEvent<HTMLCanvasElement>): NormalizedPoint | null {
        const target = { x: event.nativeEvent.offsetX / CANVAS_SIZE, y: event.nativeEvent.offsetY / CANVAS_SIZE };
        return findNearestPoint(points, target, HIT_TEST_RADIUS);
    }

    function handleClick(event: MouseEvent<HTMLCanvasElement>): void {
        const nearest = hitTest(event);
        if (nearest !== null) {
            onSelect(nearest.sampleHash);
        }
    }

    function handleDoubleClick(event: MouseEvent<HTMLCanvasElement>): void {
        const nearest = hitTest(event);
        if (nearest !== null) {
            onFocus(nearest.sampleHash);
        }
    }

    return (
        <TransformWrapper>
            <TransformComponent>
                <canvas
                    ref={canvasRef}
                    width={CANVAS_SIZE}
                    height={CANVAS_SIZE}
                    onClick={handleClick}
                    onDoubleClick={handleDoubleClick}
                />
            </TransformComponent>
        </TransformWrapper>
    );
}
