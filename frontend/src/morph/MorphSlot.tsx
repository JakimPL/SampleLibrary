import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import { useLayoutMode } from "../layout/useLayoutMode";
import { useSamplePreview } from "../samples/useSamplePreview";
import { classNames } from "../shared/classNames";
import { shortHash } from "../shared/format";
import { hintFor } from "../shared/hints";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import { type MorphEnd, useMorphStore } from "./morphStore";

/** The letter each end goes by on screen. */
export const END_LETTERS: Readonly<Record<MorphEnd, string>> = { first: "A", second: "B" };

interface MorphSlotProps {
    readonly end: MorphEnd;
    /** The sample this end holds, or `null` while it waits for one. */
    readonly hash: string | null;
    /** What the other end holds, which this one leaves to it. */
    readonly otherHash: string | null;
    /** The sample in hand, which an empty end offers. */
    readonly inHand: string | null;
}

interface EndProps {
    readonly end: MorphEnd;
    readonly hash: string;
}

/** A sample's name as the catalog states it, or `null` until it has answered. */
function useSampleName(hash: string): string | null {
    const preview = useSamplePreview(hash);
    return preview.status === "success" ? preview.data.display_name : null;
}

function Letter({ end }: { readonly end: MorphEnd }): ReactElement {
    return <span className="morph-slot-letter mono">{END_LETTERS[end]}</span>;
}

/** The end as chosen: its name as the link every row carries, and the × that lets it go. */
function ChosenEnd({ end, hash }: EndProps): ReactElement {
    const name = useSampleName(hash);
    const clearEnd = useMorphStore((state) => state.clearEnd);
    const { href, isHighlighted, onClick, onDoubleClick } = useEntityRowInteractions({ kind: "sample", hash });

    return (
        <div className="morph-slot morph-slot-chosen">
            <Letter end={end} />
            <Link
                to={href}
                className={classNames("morph-slot-name", isHighlighted && "is-highlighted")}
                onClickCapture={onClick}
                onDoubleClick={onDoubleClick}
            >
                {name === null ? (
                    <span className="mono">{shortHash(hash)}</span>
                ) : (
                    <OptionalLabel value={name} placeholder={UNNAMED_SAMPLE_LABEL} />
                )}
            </Link>
            <button
                type="button"
                className="morph-slot-clear"
                aria-label={`Clear ${END_LETTERS[end]}`}
                onClick={() => {
                    clearEnd(end);
                }}
            >
                ×
            </button>
        </div>
    );
}

/** An empty end offering the sample in hand. */
function OfferedEnd({ end, hash }: EndProps): ReactElement {
    const name = useSampleName(hash);
    const setFirst = useMorphStore((state) => state.setFirst);
    const setSecond = useMorphStore((state) => state.setSecond);
    const shown = name === null || name === "" ? shortHash(hash) : name;

    return (
        <button
            type="button"
            className="morph-slot morph-slot-offer"
            aria-label={`Use ${shown} as ${END_LETTERS[end]}`}
            onClick={() => {
                (end === "first" ? setFirst : setSecond)(hash);
            }}
        >
            <Letter end={end} />
            <span className="morph-slot-name">use {shown}</span>
        </button>
    );
}

/**
 * One end of the morph pair as the strip shows it: the sample it holds, the sample in hand offered
 * for it, or what fills it, worded for the input the person has.
 */
export function MorphSlot({ end, hash, otherHash, inHand }: MorphSlotProps): ReactElement {
    const { input } = useLayoutMode();
    if (hash !== null) {
        return <ChosenEnd end={end} hash={hash} />;
    }
    if (inHand !== null && inHand !== otherHash) {
        return <OfferedEnd end={end} hash={inHand} />;
    }
    return (
        <div className="morph-slot morph-slot-empty">
            <Letter end={end} />
            <span className="morph-slot-name">
                {hintFor(inHand === null ? "morphSlotEmpty" : "morphSlotOther", input)}
            </span>
        </div>
    );
}
