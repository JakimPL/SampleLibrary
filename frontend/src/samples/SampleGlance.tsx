import type { ReactElement } from "react";

import type { SamplePreview, WaveformPeak } from "../api/samples";
import { shortHash } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { CategoryBadge } from "./CategoryBadge";
import { MiniWaveform } from "./MiniWaveform";

const NO_PEAKS: readonly WaveformPeak[] = [];

interface SampleGlanceProps {
    readonly hash: string;
    readonly preview: SamplePreview;
}

/**
 * A sample at a glance, wherever one is named in passing: its name over its short hash and badge,
 * and its stored waveform. The cloud's tooltip, a tap card and a tray all read one sample this way.
 */
export function SampleGlance({ hash, preview }: SampleGlanceProps): ReactElement {
    return (
        <div className="glance">
            <div className="glance-name">
                <OptionalLabel value={preview.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
            </div>
            <div className="glance-meta">
                <span className="entity-hash mono">{shortHash(hash)}</span>
                <CategoryBadge sampleHash={hash} category={preview.category} handLabel={preview.hand_label} />
            </div>
            <MiniWaveform peaks={preview.thumbnail ?? NO_PEAKS} />
        </div>
    );
}
