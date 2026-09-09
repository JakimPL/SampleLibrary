import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { Module } from "../api/modules";
import { classNames } from "../shared/classNames";
import { formatBytes, shortHash } from "../shared/format";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";

interface ModuleRowProps {
    readonly module: Module;
}

export function ModuleRow({ module }: ModuleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick } = useEntityRowInteractions({
        kind: "module",
        hash: module.hash,
    });

    return (
        <tr
            className={classNames(isHighlighted && "is-highlighted", isFocused && "is-focused")}
            onClickCapture={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td className="cell-name">
                <Link to={href} className="cell-name-stack">
                    <span className="cell-primary">
                        <OptionalLabel value={module.title} placeholder={UNTITLED_MODULE_LABEL} />
                    </span>
                    <span className="entity-hash mono">{shortHash(module.hash)}</span>
                </Link>
            </td>
            <td className="cell-muted">{module.filename}</td>
            <td className="cell-stamp">
                <span className={`badge badge-${module.tracker}`}>{module.tracker}</span>
            </td>
            <td className="cell-muted mono cell-numeric">{module.sample_count}</td>
            <td className="cell-muted mono cell-numeric">{formatBytes(module.file_size)}</td>
        </tr>
    );
}
