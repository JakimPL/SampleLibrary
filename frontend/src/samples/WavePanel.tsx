import type { ReactElement, ReactNode } from "react";

import { classNames } from "../shared/classNames";

interface WavePanelProps {
    /** One row, as on a phone: the play button and the file to save at either side of the frame. */
    readonly compact: boolean;
    readonly playButton: ReactElement;
    /** The frame's content, a `WaveformView`, which carries any notice itself. */
    readonly view: ReactElement;
    readonly readout: string;
    /** What the transport says in the time's place while the audio is missing; the corner then stays clear. */
    readonly failure: string | null;
    /** Controls of the transport row alone, such as the rate a sample is heard at. */
    readonly controls: ReactNode;
    readonly download: ReactElement | null;
}

/**
 * The frame every player shares, in the two forms the app lays a player out in. In the compact
 * form the play button stands at the frame's left and the file to save at its right, two controls
 * of one size, so the frame sits centered between them with the time in its corner; where there is
 * no file to save, a slot of the same width keeps the row symmetric. Otherwise the frame stands
 * over a transport row holding the play button, the time, the controls and the file. The frame
 * keeps one place in the tree in both forms, so a player flipping between them keeps its waveform.
 */
export function WavePanel({
    compact,
    playButton,
    view,
    readout,
    failure,
    controls,
    download,
}: WavePanelProps): ReactElement {
    return (
        <div className={classNames("wave-panel", compact && "wave-panel-compact")}>
            {compact ? playButton : null}
            <div className="wave-panel-frame">
                {view}
                {compact && failure === null && <span className="time wave-time">{readout}</span>}
            </div>
            {compact ? (
                (download ?? <span className="wave-panel-slot" aria-hidden />)
            ) : (
                <div className="transport">
                    {playButton}
                    {failure === null ? (
                        <span className="time">{readout}</span>
                    ) : (
                        <span className="cell-muted">{failure}</span>
                    )}
                    {controls}
                    {download}
                </div>
            )}
        </div>
    );
}
