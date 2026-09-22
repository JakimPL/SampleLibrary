/** What a browser's WebGL offers the scatterplot, which draws every point into a 32-bit float buffer before the screen. */
export interface FloatRenderingSupport {
    /** Whether the browser gave a WebGL context at all. */
    readonly webgl: boolean;
    readonly textureFloat: boolean;
    readonly colorBufferFloat: boolean;
    readonly floatBlend: boolean;
    /** The GPU as the browser names it, or `null` where it keeps that to itself. */
    readonly renderer: string | null;
}

const TEXTURE_FLOAT = "OES_texture_float";
const COLOR_BUFFER_FLOAT = "WEBGL_color_buffer_float";
const FLOAT_BLEND = "EXT_float_blend";
const RENDERER_INFO = "WEBGL_debug_renderer_info";
const LOSE_CONTEXT = "WEBGL_lose_context";

export const NO_WEBGL: FloatRenderingSupport = {
    webgl: false,
    textureFloat: false,
    colorBufferFloat: false,
    floatBlend: false,
    renderer: null,
};

/** Asks a fresh canvas what its WebGL supports, and lets its context go again. */
export function probeFloatRendering(canvas: HTMLCanvasElement): FloatRenderingSupport {
    const gl = canvas.getContext("webgl");
    if (gl === null) {
        return NO_WEBGL;
    }
    const info = gl.getExtension(RENDERER_INFO);
    const renderer: unknown = info === null ? null : gl.getParameter(info.UNMASKED_RENDERER_WEBGL);
    const support: FloatRenderingSupport = {
        webgl: true,
        textureFloat: gl.getExtension(TEXTURE_FLOAT) !== null,
        colorBufferFloat: gl.getExtension(COLOR_BUFFER_FLOAT) !== null,
        floatBlend: gl.getExtension(FLOAT_BLEND) !== null,
        renderer: typeof renderer === "string" ? renderer : null,
    };
    gl.getExtension(LOSE_CONTEXT)?.loseContext();
    return support;
}

/** Whether the scatterplot's float pipeline draws here: a WebGL that renders and blends into float buffers. */
export function drawsFloat(support: FloatRenderingSupport): boolean {
    return support.webgl && support.textureFloat && support.colorBufferFloat && support.floatBlend;
}

/** Whether the node layer has to draw the points in the scatterplot's place: WebGL is there, its float pipeline is not. */
export function needsPlainDots(support: FloatRenderingSupport): boolean {
    return support.webgl && !drawsFloat(support);
}

let probed: FloatRenderingSupport | null = null;

/** The browser's support, asked once per visit and kept, since it holds for the whole visit. */
export function floatRenderingSupport(): FloatRenderingSupport {
    probed ??= probeFloatRendering(document.createElement("canvas"));
    return probed;
}
