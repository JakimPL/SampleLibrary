import type { ReactElement } from "react";

import type { Module } from "../api/modules";
import { shortHash } from "../shared/format";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";

interface ModuleGlanceProps {
    readonly hash: string;
    readonly module: Module;
}

/** A module at a glance, wherever one is named in passing: its title over its short hash and tracker. */
export function ModuleGlance({ hash, module }: ModuleGlanceProps): ReactElement {
    return (
        <div className="glance">
            <div className="glance-name">
                <OptionalLabel value={module.title} placeholder={UNTITLED_MODULE_LABEL} />
            </div>
            <div className="glance-meta">
                <span className="entity-hash mono">{shortHash(hash)}</span>
                <span className={`badge badge-${module.tracker}`}>{module.tracker}</span>
            </div>
        </div>
    );
}
