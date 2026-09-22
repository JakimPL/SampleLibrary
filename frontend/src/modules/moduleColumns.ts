import { createColumnHelper } from "@tanstack/react-table";

import type { Module } from "../api/modules";
import type { FittableColumn } from "../shared/columnFit";
import { UNTITLED_MODULE_LABEL } from "../shared/labels";

export type ModuleColumnId = "title" | "filename" | "tracker" | "sample_count" | "file_size";

const FILENAME_WIDTH_PX = 180;
const TRACKER_WIDTH_PX = 64;
const SAMPLE_COUNT_WIDTH_PX = 64;
const FILE_SIZE_WIDTH_PX = 80;

/** The modules listing's columns, in order, and how each yields as the listing narrows: the sample count first, the tracker last. */
export const MODULE_COLUMN_SPEC: readonly FittableColumn<ModuleColumnId>[] = [
    { id: "title", widthPx: null, dropOrder: null },
    { id: "filename", widthPx: FILENAME_WIDTH_PX, dropOrder: 2 },
    { id: "tracker", widthPx: TRACKER_WIDTH_PX, dropOrder: 4 },
    { id: "sample_count", widthPx: SAMPLE_COUNT_WIDTH_PX, dropOrder: 1 },
    { id: "file_size", widthPx: FILE_SIZE_WIDTH_PX, dropOrder: 3 },
];

const columnHelper = createColumnHelper<Module>();

/** The listing's columns as TanStack sorts and filters them; their widths come from `MODULE_COLUMN_SPEC`. */
export const MODULE_COLUMNS = [
    columnHelper.accessor((module) => (module.title.trim() === "" ? UNTITLED_MODULE_LABEL : module.title), {
        id: "title",
        header: "Title",
    }),
    columnHelper.accessor("filename", { header: "Filename" }),
    columnHelper.accessor("tracker", { header: "Tracker" }),
    columnHelper.accessor("sample_count", { header: "Samples" }),
    columnHelper.accessor("file_size", { header: "Size" }),
];
