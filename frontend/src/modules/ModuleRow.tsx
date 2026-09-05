import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { Module } from "../api/modules";
import { classNames } from "../shared/classNames";
import { formatBytes } from "../shared/format";
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
            onClick={onClick}
            onDoubleClick={onDoubleClick}
        >
            <td>
                <Link to={href}>
                    <OptionalLabel value={module.title} placeholder={UNTITLED_MODULE_LABEL} />
                </Link>
            </td>
            <td>{module.filename}</td>
            <td>{module.tracker}</td>
            <td>{module.sample_count}</td>
            <td>{formatBytes(module.file_size)}</td>
        </tr>
    );
}
