import { createColumnHelper } from "@tanstack/react-table";

import type { SampleSummary } from "../api/samples";
import type { InputMode } from "../layout/layoutMode";
import type { FittableColumn } from "../shared/columnFit";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";

export type SampleColumnId = "waveform" | "name" | "category" | "verdict" | "size_bytes" | "occurrence_count";

const WAVEFORM_WIDTH_PX = 76;
const CATEGORY_WIDTH_PX = 144;
/** Six slots for the stars and the heart under a pointer; one tap target for the heart alone under touch. */
const VERDICT_WIDTH_PX: Readonly<Record<InputMode, number>> = { pointer: 110, touch: 52 };
const SIZE_WIDTH_PX = 80;
const OCCURRENCES_WIDTH_PX = 84;

/** The samples listing's columns, in order, and how each yields as the listing narrows: the counts first, the verdict last. */
export function sampleColumnSpec(input: InputMode): readonly FittableColumn<SampleColumnId>[] {
    return [
        { id: "waveform", widthPx: WAVEFORM_WIDTH_PX, dropOrder: null },
        { id: "name", widthPx: null, dropOrder: null },
        { id: "category", widthPx: CATEGORY_WIDTH_PX, dropOrder: 3 },
        { id: "verdict", widthPx: VERDICT_WIDTH_PX[input], dropOrder: 4 },
        { id: "size_bytes", widthPx: SIZE_WIDTH_PX, dropOrder: 2 },
        { id: "occurrence_count", widthPx: OCCURRENCES_WIDTH_PX, dropOrder: 1 },
    ];
}

const columnHelper = createColumnHelper<SampleSummary>();

/** The listing's columns as TanStack sorts and filters them; their widths come from `sampleColumnSpec`. */
export const SAMPLE_COLUMNS = [
    columnHelper.display({ id: "waveform", header: "Waveform" }),
    columnHelper.accessor(
        (sample) => (sample.display_name.trim() === "" ? UNNAMED_SAMPLE_LABEL : sample.display_name),
        { id: "name", header: "Name" },
    ),
    columnHelper.display({ id: "category", header: "Category" }),
    columnHelper.display({ id: "verdict", header: "Rating" }),
    columnHelper.accessor("size_bytes", { header: "Size" }),
    columnHelper.accessor("occurrence_count", { header: "Occurrences" }),
];
