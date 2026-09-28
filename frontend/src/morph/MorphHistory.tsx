import type { ReactElement } from "react";

import type { WaveformPeak } from "../api/samples";
import { MiniWaveform } from "../samples/MiniWaveform";
import { SampleName } from "../samples/SampleName";
import { spokenNameOf, useSampleName } from "../samples/useSampleName";
import { useSamplePreview } from "../samples/useSamplePreview";
import { Button } from "../shared/controls/Button";
import { shortHash } from "../shared/format";
import { useSelectionStore } from "../workspace/selectionStore";
import { isHeld, MORPH_ENDS } from "./morphHistory";
import { END_LETTERS, type MorphEnd, useMorphStore } from "./morphStore";

const NO_PEAKS: readonly WaveformPeak[] = [];
const EMPTY_COLUMN = "Nothing yet.";
const FORGET_LABEL = "Forget all";
const UNDO_LABEL = "Undo";
const REDO_LABEL = "Redo";

/** How a column's caption counts its rows. */
function countOf(count: number): string {
    return count === 1 ? "1 sample" : `${String(count)} samples`;
}

interface HeldRowProps {
    readonly end: MorphEnd;
    readonly hash: string;
}

/** One sample an end has held: its thumbnail, name and short hash on the button that makes it that end again, pressed while it is. */
function HeldRow({ end, hash }: HeldRowProps): ReactElement {
    const name = useSampleName(hash);
    const preview = useSamplePreview(hash);
    const held = useMorphStore((state) => isHeld(state, end, hash));
    const setEnd = useMorphStore((state) => state.setEnd);
    const highlightEntity = useSelectionStore((state) => state.highlightEntity);
    const peaks = preview.status === "success" ? (preview.data.thumbnail ?? NO_PEAKS) : NO_PEAKS;

    function handleClick(): void {
        setEnd(end, hash);
        highlightEntity({ kind: "sample", hash });
    }

    return (
        <li>
            <button
                type="button"
                className="morph-history-row"
                aria-label={spokenNameOf(hash, name)}
                aria-pressed={held}
                onClick={handleClick}
            >
                <MiniWaveform peaks={peaks} />
                <span className="morph-history-name">
                    <SampleName hash={hash} name={name} />
                </span>
                <span className="morph-history-hash mono">{shortHash(hash)}</span>
            </button>
        </li>
    );
}

interface HeldColumnProps {
    readonly end: MorphEnd;
}

/** The samples one end has held, newest first, under a caption that names the end and counts them. */
function HeldColumn({ end }: HeldColumnProps): ReactElement {
    const column = useMorphStore((state) => state.held[end]);
    const letter = END_LETTERS[end];

    return (
        <section className="morph-history-column" aria-label={letter}>
            <div className="morph-history-caption">
                <span className="morph-history-letter mono">{letter}</span>
                <span className="cell-muted">{countOf(column.length)}</span>
            </div>
            {column.length === 0 ? (
                <p className="morph-history-empty">{EMPTY_COLUMN}</p>
            ) : (
                <ul className="morph-history-list">
                    {column.map((hash) => (
                        <HeldRow key={hash} end={end} hash={hash} />
                    ))}
                </ul>
            )}
        </section>
    );
}

/**
 * The history of the morph's ends: a column per end of the samples it has held, newest arrival
 * first, each on a button that makes it that end again, the two trading places when the sample
 * sits at the other end, and the row that is the end right now pressed. Over the columns stand
 * the undo and redo of the last change, and the button that forgets every row but the ones held
 * now. A row keeps its place for as long as it stays, so undo and redo move the pressed rows alone.
 */
export function MorphHistory(): ReactElement {
    const canUndo = useMorphStore((state) => state.past.length > 0);
    const canRedo = useMorphStore((state) => state.future.length > 0);
    const empty = useMorphStore((state) => state.held.first.length === 0 && state.held.second.length === 0);
    const undo = useMorphStore((state) => state.undo);
    const redo = useMorphStore((state) => state.redo);
    const forgetHeld = useMorphStore((state) => state.forgetHeld);

    return (
        <div className="morph-history">
            <div className="morph-history-tools">
                <Button variant="secondary" icon aria-label={UNDO_LABEL} disabled={!canUndo} onClick={undo}>
                    ↶
                </Button>
                <Button variant="secondary" icon aria-label={REDO_LABEL} disabled={!canRedo} onClick={redo}>
                    ↷
                </Button>
                <Button variant="quiet" disabled={empty} onClick={forgetHeld}>
                    {FORGET_LABEL}
                </Button>
            </div>
            <div className="morph-history-columns">
                {MORPH_ENDS.map((end) => (
                    <HeldColumn key={end} end={end} />
                ))}
            </div>
        </div>
    );
}
