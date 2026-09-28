import type { ReactElement } from "react";

import { shortHash } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";

interface SampleNameProps {
    readonly hash: string;
    /** The name as the catalog states it, or `null` until it has answered. */
    readonly name: string | null;
}

/** A sample's name as a control shows it: the short hash in mono until the catalog answers, then the name or the unnamed label. */
export function SampleName({ hash, name }: SampleNameProps): ReactElement {
    if (name === null) {
        return <span className="mono">{shortHash(hash)}</span>;
    }
    return <OptionalLabel value={name} placeholder={UNNAMED_SAMPLE_LABEL} />;
}
