import type { MouseEvent, ReactElement } from "react";
import { useEffect, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";

import { ErrorNotice } from "../shared/ErrorNotice";
import { Loading } from "../shared/Loading";
import { findNearestPoint, normalizePoints } from "./geometry";
import { useCloud } from "./useCloud";

const CANVAS_SIZE = 800;
const POINT_RADIUS = 3;
const HIT_TEST_RADIUS = 0.02;
// eslint-disable-next-line @typescript-eslint/no-magic-numbers -- 2π reads clearer as a literal multiplication than a precomputed constant
const FULL_CIRCLE_RADIANS = 2 * Math.PI;

export function CloudPage(): ReactElement {
    const state = useCloud();
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const navigate = useNavigate();
    const points = useMemo(() => (state.status === "success" ? normalizePoints(state.data) : []), [state]);

    useEffect(() => {
        const context = canvasRef.current?.getContext("2d");
        if (!context) {
            return;
        }

        context.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
        context.fillStyle = "currentColor";
        for (const point of points) {
            context.beginPath();
            context.arc(point.x * CANVAS_SIZE, point.y * CANVAS_SIZE, POINT_RADIUS, 0, FULL_CIRCLE_RADIANS);
            context.fill();
        }
    }, [points]);

    function handleClick(event: MouseEvent<HTMLCanvasElement>): void {
        const target = { x: event.nativeEvent.offsetX / CANVAS_SIZE, y: event.nativeEvent.offsetY / CANVAS_SIZE };
        const nearest = findNearestPoint(points, target, HIT_TEST_RADIUS);
        if (nearest !== null) {
            void navigate(`/samples/${nearest.sampleHash}`);
        }
    }

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    return (
        <section>
            <h1>Sample cloud</h1>
            <TransformWrapper>
                <TransformComponent>
                    <canvas ref={canvasRef} width={CANVAS_SIZE} height={CANVAS_SIZE} onClick={handleClick} />
                </TransformComponent>
            </TransformWrapper>
        </section>
    );
}
