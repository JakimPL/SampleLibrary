import { describe, expect, it } from "vitest";

import { defaultSerializedLayout } from "../../src/workspace/defaultLayout";
import {
    LAYOUT_STORAGE_KEY,
    LAYOUT_VERSION,
    resetLayout,
    restoreOrBuildLayout,
    type StoredLayout,
} from "../../src/workspace/dockviewPersistence";
import { PANEL_REGISTRY, type PanelId } from "../../src/workspace/panelRegistry";
import { FakeDockviewApi, serializedLayoutOf } from "../support/fakeDockviewApi";

const RETIRED_KNOWN_PANELS_STORAGE_KEY = "samplelibrary-workspace-panels";
const ALL_PANEL_IDS = Object.keys(PANEL_REGISTRY) as PanelId[];

function storeRecord(record: StoredLayout): void {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(record));
}

function storedRecord(): StoredLayout {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (raw === null) {
        throw new Error("no record stored");
    }
    return JSON.parse(raw) as StoredLayout;
}

describe("restoreOrBuildLayout", () => {
    it("draws the first-run arrangement when nothing was saved", () => {
        const api = new FakeDockviewApi([]);

        restoreOrBuildLayout(api.asApi());

        expect(api.fromJSON).toHaveBeenCalledWith(defaultSerializedLayout());
    });

    it("restores a record of the current version as it was saved", () => {
        const saved = serializedLayoutOf(["cloud", "stats"]);
        storeRecord({ version: LAYOUT_VERSION, layout: saved, knownPanels: ALL_PANEL_IDS });
        const api = new FakeDockviewApi(["cloud", "stats"]);

        restoreOrBuildLayout(api.asApi());

        expect(api.fromJSON).toHaveBeenCalledWith(saved);
        expect(api.addPanel).not.toHaveBeenCalled();
    });

    it("discards a record of another version, with the key an older build kept beside it", () => {
        storeRecord({ version: LAYOUT_VERSION - 1, layout: serializedLayoutOf(["cloud"]), knownPanels: ALL_PANEL_IDS });
        localStorage.setItem(RETIRED_KNOWN_PANELS_STORAGE_KEY, JSON.stringify(ALL_PANEL_IDS));
        const api = new FakeDockviewApi([]);

        restoreOrBuildLayout(api.asApi());

        expect(api.fromJSON).toHaveBeenCalledWith(defaultSerializedLayout());
        expect(localStorage.getItem(LAYOUT_STORAGE_KEY)).toBeNull();
        expect(localStorage.getItem(RETIRED_KNOWN_PANELS_STORAGE_KEY)).toBeNull();
    });

    it("discards an arrangement saved bare, before records carried a version", () => {
        localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(serializedLayoutOf(["cloud"])));
        const api = new FakeDockviewApi([]);

        restoreOrBuildLayout(api.asApi());

        expect(api.fromJSON).toHaveBeenCalledWith(defaultSerializedLayout());
    });

    it("draws the first-run arrangement again when the saved one cannot be read back", () => {
        storeRecord({ version: LAYOUT_VERSION, layout: serializedLayoutOf(["cloud"]), knownPanels: ALL_PANEL_IDS });
        const api = new FakeDockviewApi([]);
        api.fromJSON.mockImplementationOnce(() => {
            throw new Error("a group named no panel");
        });

        restoreOrBuildLayout(api.asApi());

        expect(api.fromJSON).toHaveBeenLastCalledWith(defaultSerializedLayout());
    });

    it("opens a panel registered after the record was saved, and saves the completed arrangement", () => {
        const knownBefore = ALL_PANEL_IDS.filter((id) => id !== "stats");
        storeRecord({ version: LAYOUT_VERSION, layout: serializedLayoutOf(knownBefore), knownPanels: knownBefore });
        const api = new FakeDockviewApi(knownBefore);

        restoreOrBuildLayout(api.asApi());

        expect(api.addPanel).toHaveBeenCalledWith(expect.objectContaining({ id: "stats" }));
        expect(storedRecord().knownPanels).toEqual(ALL_PANEL_IDS);
    });

    it("saves a versioned record naming every registered panel on each layout change", () => {
        const api = new FakeDockviewApi(ALL_PANEL_IDS);
        restoreOrBuildLayout(api.asApi());

        api.emitLayoutChange();

        const record = storedRecord();
        expect(record.version).toBe(LAYOUT_VERSION);
        expect(record.knownPanels).toEqual(ALL_PANEL_IDS);
        expect(record.layout).toEqual(api.toJSON());
    });
});

describe("resetLayout", () => {
    it("forgets the saved record and draws the first-run arrangement", () => {
        storeRecord({ version: LAYOUT_VERSION, layout: serializedLayoutOf(["cloud"]), knownPanels: ALL_PANEL_IDS });
        const api = new FakeDockviewApi(["cloud"]);

        resetLayout(api.asApi());

        expect(localStorage.getItem(LAYOUT_STORAGE_KEY)).toBeNull();
        expect(api.fromJSON).toHaveBeenCalledWith(defaultSerializedLayout());
    });
});
