import type { ReactElement } from "react";

const SAVE_GLYPH = "⤓";

interface DownloadLinkProps {
    readonly href: string;
    readonly fileName: string;
    readonly label: string;
}

/**
 * A link that saves what it points at rather than opening it, standing among a transport's own
 * controls.
 *
 * The name the file is saved under travels with the link, which a browser honors for an address on
 * the application's own origin -- every audio route is served under the API's prefix, so a saved
 * sample or render arrives named as the library calls it.
 */
export function DownloadLink({ href, fileName, label }: DownloadLinkProps): ReactElement {
    return (
        <a className="download-link" href={href} download={fileName} aria-label={label} title={label}>
            {SAVE_GLYPH}
        </a>
    );
}
