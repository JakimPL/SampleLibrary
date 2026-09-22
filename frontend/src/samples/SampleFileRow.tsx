import type { ReactElement } from "react";

import type { SampleDetail } from "../api/samples";

type SampleFile = SampleDetail["files"][number];

/** The columns of the files table, as its header and its stacked rows both name them. */
export const FILE_COLUMN_LABELS = { file: "File", directory: "Directory", rate: "Rate", status: "Status" } as const;

interface SampleFileRowProps {
    readonly sampleFile: SampleFile;
}

/** One file of a sample directory a sample was found in, marked when the file is gone or changed since its scan. */
export function SampleFileRow({ sampleFile }: SampleFileRowProps): ReactElement {
    return (
        <tr>
            <td className="cell-name" data-label={FILE_COLUMN_LABELS.file}>
                <span className="cell-primary">{sampleFile.location.relative_path}</span>
            </td>
            <td className="cell-muted" data-label={FILE_COLUMN_LABELS.directory}>
                {sampleFile.location.directory}
            </td>
            <td className="mono" data-label={FILE_COLUMN_LABELS.rate}>
                {sampleFile.rate}
            </td>
            <td data-label={FILE_COLUMN_LABELS.status}>
                {!sampleFile.available && <span className="badge badge-unavailable">unavailable</span>}
            </td>
        </tr>
    );
}
