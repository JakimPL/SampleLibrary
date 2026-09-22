import type { ReactElement } from "react";
import { Link } from "react-router-dom";

import type { Module } from "../api/modules";
import { classNames } from "../shared/classNames";
import { formatBytes, shortHash } from "../shared/format";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { RowOpenLink } from "../workspace/RowOpenLink";
import { useEntityRowInteractions } from "../workspace/useEntityRowInteractions";
import type { ModuleColumnId } from "./moduleColumns";

interface ModuleRowProps {
    readonly module: Module;
    /** The columns the listing shows at its width; the title is always among them. */
    readonly visibleColumns: ReadonlySet<ModuleColumnId>;
}

export function ModuleRow({ module, visibleColumns }: ModuleRowProps): ReactElement {
    const { href, isHighlighted, isFocused, onClick, onDoubleClick, onKeyDown } = useEntityRowInteractions({
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
                <Link to={href} className="cell-name-stack" onKeyDown={onKeyDown}>
                    <span className="cell-primary">
                        <OptionalLabel value={module.title} placeholder={UNTITLED_MODULE_LABEL} />
                    </span>
                    <span className="entity-hash mono">
                        {shortHash(module.hash)}
                        {!visibleColumns.has("tracker") && (
                            <span className={`badge badge-${module.tracker}`}>{module.tracker}</span>
                        )}
                    </span>
                </Link>
                <RowOpenLink href={href} label="Open module" />
            </td>
            {visibleColumns.has("filename") && <td className="cell-muted">{module.filename}</td>}
            {visibleColumns.has("tracker") && (
                <td className="cell-stamp">
                    <span className={`badge badge-${module.tracker}`}>{module.tracker}</span>
                </td>
            )}
            {visibleColumns.has("sample_count") && (
                <td className="cell-muted mono cell-numeric">{module.sample_count}</td>
            )}
            {visibleColumns.has("file_size") && (
                <td className="cell-muted mono cell-numeric">{formatBytes(module.file_size)}</td>
            )}
        </tr>
    );
}
