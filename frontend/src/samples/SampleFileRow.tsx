import type { ReactElement } from "react";

import type { SampleDetail } from "../api/samples";

type SampleFile = SampleDetail["files"][number];

interface SampleFileRowProps {
    readonly sampleFile: SampleFile;
}

/** One file of a sample directory a sample was found in, marked when the file is gone or changed since its scan. */
export function SampleFileRow({ sampleFile }: SampleFileRowProps): ReactElement {
    return (
        <tr>
            <td className="cell-name">
                <span className="cell-primary">{sampleFile.location.relative_path}</span>
            </td>
            <td className="cell-muted">{sampleFile.location.directory}</td>
            <td className="mono">{sampleFile.rate}</td>
            <td>{!sampleFile.available && <span className="badge badge-unavailable">unavailable</span>}</td>
        </tr>
    );
}
