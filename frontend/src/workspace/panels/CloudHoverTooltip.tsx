import type { ReactElement } from "react";
import { useEffect, useRef } from "react";

import type { WaveformPeak } from "../../api/samples";
import { useModule } from "../../modules/useModule";
import { CategoryBadge } from "../../samples/CategoryBadge";
import { readMiniWaveformColor } from "../../samples/miniWaveformColor";
import { useSampleHoverPreview } from "../../samples/useSampleHoverPreview";
import { layoutWaveformBars } from "../../samples/waveformLayout";
import { shortHash } from "../../shared/format";
import { UNNAMED_SAMPLE_LABEL, UNTITLED_MODULE_LABEL } from "../../shared/labels";
import { OptionalLabel } from "../../shared/OptionalLabel";
import { useThemeSignal } from "../../theme/useThemeSignal";
import type { EntityRef } from "../selectionStore";

const WAVEFORM_WIDTH_PX = 96;
const WAVEFORM_HEIGHT_PX = 28;

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

function MiniWaveform({ peaks }: { readonly peaks: readonly WaveformPeak[] }): ReactElement {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const themeSignal = useThemeSignal();

    useEffect(() => {
        const context = canvasRef.current?.getContext("2d");
        if (!context) {
            return;
        }

        context.clearRect(0, 0, WAVEFORM_WIDTH_PX, WAVEFORM_HEIGHT_PX);
        context.fillStyle = readMiniWaveformColor();
        for (const bar of layoutWaveformBars(peaks, WAVEFORM_WIDTH_PX, WAVEFORM_HEIGHT_PX)) {
            context.fillRect(bar.x, bar.yTop, bar.width, bar.yBottom - bar.yTop);
        }
    }, [peaks, themeSignal.preference, themeSignal.systemVersion]);

    return <canvas ref={canvasRef} width={WAVEFORM_WIDTH_PX} height={WAVEFORM_HEIGHT_PX} />;
}

function SampleHoverTooltip({ hash, x, y }: EntityTooltipProps): ReactElement | null {
    const state = useSampleHoverPreview(hash);
    if (state.status !== "success") {
        return null;
    }

    return (
        <div className="cloud-hover-tooltip" style={{ left: x, top: y }}>
            <div className="cloud-hover-name">
                <OptionalLabel value={state.data.displayName} placeholder={UNNAMED_SAMPLE_LABEL} />
            </div>
            <div className="cloud-hover-meta">
                <span className="entity-hash mono">{shortHash(hash)}</span>
                <CategoryBadge sampleHash={hash} category={state.data.category} handLabel={state.data.handLabel} />
            </div>
            <MiniWaveform peaks={state.data.peaks} />
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
            <div className="cloud-hover-name">
                <OptionalLabel value={state.data.title} placeholder={UNTITLED_MODULE_LABEL} />
            </div>
            <div className="cloud-hover-meta">
                <span className="entity-hash mono">{shortHash(hash)}</span>
                <span className={`badge badge-${state.data.tracker}`}>{state.data.tracker}</span>
            </div>
        </div>
    );
}

/**
 * A minimal popup for whichever point the cursor is currently over: a name (or the shared
 * "unnamed"/"untitled" placeholder), a short git-style abbreviated hash as a stable identity even
 * for an unnamed sample, and -- for a sample -- a compact waveform preview. Positioned at the
 * point's own screen coordinates, which `CloudView` reports through its `onHover` callback.
 */
export function CloudHoverTooltip({ entity, x, y }: CloudHoverTooltipProps): ReactElement | null {
    return entity.kind === "sample" ? (
        <SampleHoverTooltip hash={entity.hash} x={x} y={y} />
    ) : (
        <ModuleHoverTooltip hash={entity.hash} x={x} y={y} />
    );
}
