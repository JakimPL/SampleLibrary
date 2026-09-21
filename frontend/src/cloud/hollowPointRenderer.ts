import createRegl from "regl";

import type { PointShape } from "./cloudRenderSettings";
import { devicePixels } from "./markerGeometry";
import type { NodeGeometry } from "./nodeGeometry";
import type { ViewTransform } from "./viewTransform";

/** How one frame of nodes looks: the marker's shape and sizes in CSS pixels, and how opaque its inside is. */
export interface NodeFrameStyle {
    readonly shape: PointShape;
    readonly sizePx: number;
    readonly lineWidthPx: number;
    readonly fillOpacity: number;
}

/** Draws a cloud's points as hollow markers of one size on a canvas of its own. */
export interface HollowPointRenderer {
    readonly setGeometry: (geometry: NodeGeometry) => void;
    /** One RGBA byte quadruple per palette slot. */
    readonly setPalette: (palette: Uint8Array) => void;
    readonly draw: (transform: ViewTransform, style: NodeFrameStyle) => void;
    readonly clear: () => void;
    readonly destroy: () => void;
}

interface NodeProps {
    readonly rowX: number[];
    readonly rowY: number[];
    readonly deviceScale: number[];
    readonly bufferSize: number[];
    readonly pointSize: number;
    readonly lineWidth: number;
    readonly snapOffset: number;
    readonly square: number;
    readonly fillOpacity: number;
    readonly paletteSize: number;
    readonly count: number;
}

interface NodeUniforms extends createRegl.Uniforms {
    rowX: number[];
    rowY: number[];
    deviceScale: number[];
    bufferSize: number[];
    pointSize: number;
    lineWidth: number;
    snapOffset: number;
    square: number;
    fillOpacity: number;
    palette: createRegl.Texture2D;
    paletteSize: number;
}

interface NodeAttributes extends createRegl.Attributes {
    position: createRegl.Buffer;
    slot: createRegl.Buffer;
}

const SQUARE_SHAPE = "square";
const BYTES_PER_COLOR = 4;
const ODD_SIZE_SNAP = 0.5;
const EVEN_SIZE_SNAP = 0;
const PARITY = 2;
const TRANSPARENT: [number, number, number, number] = [0, 0, 0, 0];
const CONTEXT_ATTRIBUTES: WebGLContextAttributes = {
    alpha: true,
    antialias: false,
    depth: false,
    stencil: false,
    premultipliedAlpha: true,
    preserveDrawingBuffer: false,
};

const VERTEX_SHADER = `
precision highp float;
attribute vec2 position;
attribute float slot;
uniform vec3 rowX;
uniform vec3 rowY;
uniform vec2 deviceScale;
uniform vec2 bufferSize;
uniform float pointSize;
uniform float snapOffset;
uniform sampler2D palette;
uniform float paletteSize;
varying vec4 color;

void main() {
    vec3 homogeneous = vec3(position, 1.0);
    vec2 device = vec2(dot(rowX, homogeneous), dot(rowY, homogeneous)) * deviceScale;
    device = floor(device + 0.5 - snapOffset) + snapOffset;
    gl_Position = vec4(device.x / bufferSize.x * 2.0 - 1.0, 1.0 - device.y / bufferSize.y * 2.0, 0.0, 1.0);
    gl_PointSize = pointSize;
    color = texture2D(palette, vec2((slot + 0.5) / paletteSize, 0.5));
}
`;

const FRAGMENT_SHADER = `
precision highp float;
uniform float pointSize;
uniform float lineWidth;
uniform float square;
uniform float fillOpacity;
varying vec4 color;

void main() {
    vec2 pixel = gl_PointCoord * pointSize;
    float coverage;
    if (square > 0.5) {
        vec2 fromEdge = min(pixel, vec2(pointSize) - pixel);
        coverage = min(fromEdge.x, fromEdge.y) < lineWidth ? 1.0 : fillOpacity;
    } else {
        float radius = pointSize * 0.5;
        float distance = length(pixel - vec2(radius));
        float withinOuter = clamp(radius - distance + 0.5, 0.0, 1.0);
        float ring = withinOuter * clamp(distance - (radius - lineWidth) + 0.5, 0.0, 1.0);
        float inside = clamp(radius - lineWidth - distance + 0.5, 0.0, 1.0);
        coverage = max(ring, inside * fillOpacity);
    }
    float alpha = coverage * color.a;
    if (alpha <= 0.0) {
        discard;
    }
    gl_FragColor = vec4(color.rgb * alpha, alpha);
}
`;

/**
 * The node layer's WebGL boundary, wrapping regl behind the few operations the cloud needs. It
 * answers null where the canvas yields no WebGL context -- jsdom, or a browser with WebGL turned
 * off -- and the cloud then shows its dots alone.
 *
 * A marker's size and stroke round to whole device pixels and its center snaps to the device grid --
 * an odd-sized marker centered on a pixel, an even-sized one on a pixel corner --
 * so a one-pixel frame stays one crisp pixel at any pixel density and every marker keeps one size
 * whatever the zoom, the way OpenMPT's envelope nodes do.
 */
export function createHollowPointRenderer(canvas: HTMLCanvasElement): HollowPointRenderer | null {
    const gl = canvas.getContext("webgl", CONTEXT_ATTRIBUTES);
    if (gl === null) {
        return null;
    }
    const regl = createRegl({ gl });
    const positionBuffer = regl.buffer({ usage: "static", type: "float", length: 0 });
    const slotBuffer = regl.buffer({ usage: "static", type: "float", length: 0 });
    const palette = regl.texture({ width: 1, height: 1, data: new Uint8Array(BYTES_PER_COLOR) });
    let count = 0;
    let paletteSize = 1;

    const drawNodes = regl<NodeUniforms, NodeAttributes, NodeProps>({
        vert: VERTEX_SHADER,
        frag: FRAGMENT_SHADER,
        attributes: { position: positionBuffer, slot: slotBuffer },
        uniforms: {
            rowX: regl.prop<NodeProps, "rowX">("rowX"),
            rowY: regl.prop<NodeProps, "rowY">("rowY"),
            deviceScale: regl.prop<NodeProps, "deviceScale">("deviceScale"),
            bufferSize: regl.prop<NodeProps, "bufferSize">("bufferSize"),
            pointSize: regl.prop<NodeProps, "pointSize">("pointSize"),
            lineWidth: regl.prop<NodeProps, "lineWidth">("lineWidth"),
            snapOffset: regl.prop<NodeProps, "snapOffset">("snapOffset"),
            square: regl.prop<NodeProps, "square">("square"),
            fillOpacity: regl.prop<NodeProps, "fillOpacity">("fillOpacity"),
            palette,
            paletteSize: regl.prop<NodeProps, "paletteSize">("paletteSize"),
        },
        count: regl.prop<NodeProps, "count">("count"),
        primitive: "points",
        depth: { enable: false },
        blend: {
            enable: true,
            func: { srcRGB: "one", srcAlpha: "one", dstRGB: "one minus src alpha", dstAlpha: "one minus src alpha" },
        },
    });

    function resize(transform: ViewTransform): void {
        const width = devicePixels(transform.widthPx, transform.devicePixelRatio);
        const height = devicePixels(transform.heightPx, transform.devicePixelRatio);
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        regl.poll();
    }

    return {
        setGeometry(geometry: NodeGeometry): void {
            positionBuffer({ usage: "static", type: "float", data: geometry.positions });
            slotBuffer({ usage: "static", type: "float", data: geometry.slots });
            count = geometry.count;
        },
        setPalette(bytes: Uint8Array): void {
            paletteSize = Math.max(1, Math.floor(bytes.length / BYTES_PER_COLOR));
            palette({ width: paletteSize, height: 1, data: bytes, min: "nearest", mag: "nearest" });
        },
        draw(transform: ViewTransform, style: NodeFrameStyle): void {
            resize(transform);
            regl.clear({ color: TRANSPARENT });
            if (count === 0) {
                return;
            }
            const pointSize = Math.min(
                devicePixels(style.sizePx, transform.devicePixelRatio),
                regl.limits.pointSizeDims[1] ?? 1,
            );
            drawNodes({
                rowX: [transform.xx, transform.xy, transform.offsetX],
                rowY: [transform.yx, transform.yy, transform.offsetY],
                deviceScale: [canvas.width / transform.widthPx, canvas.height / transform.heightPx],
                bufferSize: [canvas.width, canvas.height],
                pointSize,
                lineWidth: style.lineWidthPx > 0 ? devicePixels(style.lineWidthPx, transform.devicePixelRatio) : 0,
                snapOffset: pointSize % PARITY === 1 ? ODD_SIZE_SNAP : EVEN_SIZE_SNAP,
                square: style.shape === SQUARE_SHAPE ? 1 : 0,
                fillOpacity: style.fillOpacity,
                paletteSize,
                count,
            });
        },
        clear(): void {
            regl.poll();
            regl.clear({ color: TRANSPARENT });
        },
        destroy(): void {
            regl.destroy();
        },
    };
}
