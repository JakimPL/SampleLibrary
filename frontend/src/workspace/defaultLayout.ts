import { type DockviewApi, Orientation, type SerializedDockview } from "dockview-react";

import { PANEL_REGISTRY, type PanelId } from "./panelRegistry";

interface LayoutRow {
    readonly share: number;
    /** The row's tabs in order; the first is the one in front. */
    readonly panels: readonly [PanelId, ...PanelId[]];
}

interface LayoutColumn {
    readonly share: number;
    readonly rows: readonly [LayoutRow, ...LayoutRow[]];
}

/** The box the arrangement is drawn in; dockview scales it to the window it opens in. */
const NOMINAL_WIDTH_PX = 1000;
const NOMINAL_HEIGHT_PX = 600;
const WHOLE_SHARE = 1;
const LISTINGS_COLUMN_SHARE = 0.38;
const CLOUD_COLUMN_SHARE = 0.34;
const INSPECTOR_COLUMN_SHARE = 0.28;
const CLOUD_ROW_SHARE = 0.68;
const TRANSPORT_ROW_SHARE = 0.32;

/**
 * The first-run arrangement: the listings on the left, the cloud over the transport in the
 * middle, and an inspector of the details and the statistics on the right.
 */
const DEFAULT_COLUMNS: readonly LayoutColumn[] = [
    { share: LISTINGS_COLUMN_SHARE, rows: [{ share: WHOLE_SHARE, panels: ["samples-list", "modules-list"] }] },
    {
        share: CLOUD_COLUMN_SHARE,
        rows: [
            { share: CLOUD_ROW_SHARE, panels: ["cloud"] },
            { share: TRANSPORT_ROW_SHARE, panels: ["waveform", "morph"] },
        ],
    },
    {
        share: INSPECTOR_COLUMN_SHARE,
        rows: [{ share: WHOLE_SHARE, panels: ["sample-detail", "module-detail", "stats"] }],
    },
];

type GridNode = SerializedDockview["grid"]["root"];

function groupId(columnIndex: number, rowIndex: number): string {
    return `column-${String(columnIndex + 1)}-row-${String(rowIndex + 1)}`;
}

function leafOf(row: LayoutRow, columnIndex: number, rowIndex: number, size: number): GridNode {
    return {
        type: "leaf",
        data: { views: [...row.panels], activeView: row.panels[0], id: groupId(columnIndex, rowIndex) },
        size,
    };
}

function columnNode(column: LayoutColumn, columnIndex: number): GridNode {
    const width = Math.round(NOMINAL_WIDTH_PX * column.share);
    if (column.rows.length === 1) {
        return leafOf(column.rows[0], columnIndex, 0, width);
    }
    return {
        type: "branch",
        data: column.rows.map((row, rowIndex) =>
            leafOf(row, columnIndex, rowIndex, Math.round(NOMINAL_HEIGHT_PX * row.share)),
        ),
        size: width,
    };
}

function panelStates(): SerializedDockview["panels"] {
    return Object.fromEntries(
        Object.values(PANEL_REGISTRY).map((definition) => [
            definition.id,
            {
                id: definition.id,
                contentComponent: definition.id,
                title: definition.title,
                renderer: definition.renderer,
            },
        ]),
    );
}

/**
 * The first-run arrangement as dockview reads it back, drawn from `DEFAULT_COLUMNS` over the
 * nominal box, with the listings' group in front.
 */
export function defaultSerializedLayout(): SerializedDockview {
    return {
        grid: {
            root: { type: "branch", data: DEFAULT_COLUMNS.map(columnNode), size: NOMINAL_HEIGHT_PX },
            width: NOMINAL_WIDTH_PX,
            height: NOMINAL_HEIGHT_PX,
            orientation: Orientation.HORIZONTAL,
        },
        panels: panelStates(),
        activeGroup: groupId(0, 0),
    };
}

/** Replaces whatever the shell holds with the first-run arrangement. */
export function buildDefaultLayout(api: DockviewApi): void {
    api.fromJSON(defaultSerializedLayout());
}
