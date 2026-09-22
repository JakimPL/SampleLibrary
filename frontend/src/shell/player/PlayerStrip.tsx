import type { ReactElement } from "react";

import { morphPreview } from "../../morph/morphPreview";
import { useMorphStore } from "../../morph/morphStore";
import { useEndpoint } from "../../morph/useEndpoint";
import { useAudioPreview } from "../../samples/useAudioPreview";
import { classNames } from "../../shared/classNames";
import { UNNAMED_SAMPLE_LABEL } from "../../shared/labels";
import { OptionalLabel } from "../../shared/OptionalLabel";
import { useSelectionStore } from "../../workspace/selectionStore";
import { FocusedSampleTransport } from "./FocusedSampleTransport";
import { usePlayerStripStore } from "./playerStripStore";

const WEIGHT_DECIMAL_PLACES = 2;

interface PlayerStripProps {
    /** Brings the Morph panel forward, which the strip offers while a morph is what sounds. */
    readonly onRevealMorph: () => void;
}

interface MorphReadoutProps {
    readonly first: string;
    readonly second: string;
    readonly weight: number;
    readonly onReveal: () => void;
}

function EndName({ hash }: { readonly hash: string }): ReactElement {
    const reading = useEndpoint(hash);
    return <OptionalLabel value={reading.name} placeholder={UNNAMED_SAMPLE_LABEL} />;
}

/** One line naming the morph now sounding, with the way to the panel that drew it. */
function MorphReadout({ first, second, weight, onReveal }: MorphReadoutProps): ReactElement {
    return (
        <div className="player-strip-morph" role="status">
            <span className="cell-muted">Morph</span>
            <EndName hash={first} />
            <span className="cell-muted">⇄</span>
            <EndName hash={second} />
            <span className="mono cell-muted">{weight.toFixed(WEIGHT_DECIMAL_PLACES)}</span>
            <button type="button" className="player-strip-morph-show" onClick={onReveal}>
                Show
            </button>
        </div>
    );
}

/**
 * The window-level player under the workspace: the focused sample's transport and waveform, the
 * waveform folded away when the strip is collapsed, and a line naming a morph while its render is
 * what sounds. It stays out of the way until a sample is focused or a morph plays, and the View
 * menu can take it away altogether.
 */
export function PlayerStrip({ onRevealMorph }: PlayerStripProps): ReactElement | null {
    const visible = usePlayerStripStore((state) => state.visible);
    const expanded = usePlayerStripStore((state) => state.expanded);
    const toggleExpanded = usePlayerStripStore((state) => state.toggleExpanded);
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);
    const first = useMorphStore((state) => state.first);
    const second = useMorphStore((state) => state.second);
    const weight = useMorphStore((state) => state.weight);
    const { playingKey } = useAudioPreview();
    const pair = first !== null && second !== null ? { first, second } : null;
    const soundingPair =
        pair !== null && playingKey === morphPreview(pair.first, pair.second, weight).key ? pair : null;

    if (!visible || (focusedSampleHash === null && soundingPair === null)) {
        return null;
    }

    return (
        <div
            className={classNames("player-strip", expanded && "player-strip-expanded")}
            role="region"
            aria-label="Player"
        >
            {soundingPair !== null && (
                <MorphReadout
                    first={soundingPair.first}
                    second={soundingPair.second}
                    weight={weight}
                    onReveal={onRevealMorph}
                />
            )}
            {focusedSampleHash !== null && (
                <FocusedSampleTransport sampleHash={focusedSampleHash} layout={expanded ? "strip" : "transport"} />
            )}
            <button
                type="button"
                className="player-strip-toggle"
                aria-label={expanded ? "Collapse the player" : "Expand the player"}
                aria-expanded={expanded}
                onClick={toggleExpanded}
            >
                {expanded ? "⌄" : "⌃"}
            </button>
        </div>
    );
}
