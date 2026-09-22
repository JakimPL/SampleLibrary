import type { ReactElement } from "react";

import { type CloudDots, useCloudDotsStore } from "../cloud/cloudDotsStore";
import { drawsFloat, type FloatRenderingSupport } from "../cloud/floatRendering";
import type { InputMode, LayoutMode } from "../layout/layoutMode";
import { useLayoutMode } from "../layout/useLayoutMode";
import { BottomSheet } from "../shared/overlay/BottomSheet";

export const DIAGNOSTICS_TITLE = "Diagnostics";

interface DiagnosticsSheetProps {
    readonly support: FloatRenderingSupport;
    readonly onClose: () => void;
}

interface Fact {
    readonly name: string;
    readonly value: string;
}

interface DotsChoice {
    readonly dots: CloudDots;
    readonly label: string;
}

const DOTS_CHOICES: readonly DotsChoice[] = [
    { dots: "auto", label: "As the browser allows" },
    { dots: "plain", label: "Plain dots" },
];

function yesOrNo(supported: boolean): string {
    return supported ? "yes" : "no";
}

/** How the cloud's points draw here, in one line. */
function cloudPointsFact(support: FloatRenderingSupport): string {
    if (!support.webgl) {
        return "nothing draws without WebGL";
    }
    return drawsFloat(support) ? "the scatterplot draws them" : "plain dots stand in, since float blending is missing";
}

function factsOf(support: FloatRenderingSupport, layout: LayoutMode, input: InputMode): readonly Fact[] {
    return [
        { name: "Browser", value: navigator.userAgent },
        {
            name: "Screen",
            value: `${String(window.innerWidth)} × ${String(window.innerHeight)} at ${String(window.devicePixelRatio)}×`,
        },
        { name: "Layout", value: `${layout}, ${input}` },
        { name: "WebGL", value: support.webgl ? (support.renderer ?? "available") : "unavailable" },
        { name: "Float textures", value: yesOrNo(support.textureFloat) },
        { name: "Float color buffers", value: yesOrNo(support.colorBufferFloat) },
        { name: "Float blending", value: yesOrNo(support.floatBlend) },
        { name: "Cloud points", value: cloudPointsFact(support) },
    ];
}

/**
 * What this browser gives the app, readable on a phone with no console: the screen and the layout,
 * what its WebGL supports and how the cloud's points draw as a result, with the choice to draw
 * them as plain dots regardless.
 */
export function DiagnosticsSheet({ support, onClose }: DiagnosticsSheetProps): ReactElement {
    const { layout, input } = useLayoutMode();
    const dots = useCloudDotsStore((state) => state.dots);
    const setDots = useCloudDotsStore((state) => state.setDots);

    return (
        <BottomSheet title={DIAGNOSTICS_TITLE} onClose={onClose}>
            <dl className="fact-list">
                {factsOf(support, layout, input).map((fact) => (
                    <div key={fact.name} className="fact">
                        <dt className="fact-name">{fact.name}</dt>
                        <dd className="fact-value">{fact.value}</dd>
                    </div>
                ))}
            </dl>
            <fieldset className="diagnostics-choice">
                <legend>Draw the points</legend>
                {DOTS_CHOICES.map((choice) => (
                    <label key={choice.dots}>
                        <input
                            type="radio"
                            name="cloud-dots"
                            value={choice.dots}
                            checked={dots === choice.dots}
                            onChange={() => {
                                setDots(choice.dots);
                            }}
                        />
                        {choice.label}
                    </label>
                ))}
            </fieldset>
        </BottomSheet>
    );
}
