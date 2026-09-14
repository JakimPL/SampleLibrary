import type { ServerResponse } from "node:http";

import type { Connect, Plugin, ViteDevServer } from "vite";

import type { components } from "../src/api/schema";
import { seedLayout } from "./cloudSeed";
import { densifyPoints, parseDensifyTarget, type PlanarPoint } from "./densifyCloud";

type CloudPoint = components["schemas"]["SampleCloudPoint"];
type ModuleCloudPoint = components["schemas"]["ModuleCloudPoint"];
type SampleSummary = components["schemas"]["SampleSummary"];
type ModuleSummary = components["schemas"]["Module"];

interface Page<Item> {
    readonly items: readonly Item[];
}

export interface DensifyCloudPluginOptions {
    /** Where the API answers, the same origin the `/api` proxy forwards to. */
    readonly backendUrl: string;
    /** The value of `VITE_CLOUD_DENSIFY`: how many sample points to answer with. */
    readonly sampleTargetText: string | undefined;
    /** The value of `VITE_CLOUD_DENSIFY_MODULES`: how many module points to answer with. */
    readonly moduleTargetText: string | undefined;
}

const PLUGIN_NAME = "samplelibrary:densify-cloud";
const SAMPLE_CLOUD_PATH = "/api/cloud";
const MODULE_CLOUD_PATH = "/api/cloud/modules";
const SAMPLE_LISTING_PATH = "/api/samples";
const MODULE_LISTING_PATH = "/api/modules";
const GET_METHOD = "GET";
const URL_BASE = "http://localhost";
const JSON_CONTENT_TYPE = "application/json";
const DENSIFY_SEED = 20260914;
const UNCATEGORIZED_CATEGORY = "uncategorized";
const UNCATEGORIZED_CLUSTER_WEIGHT = 8;
const UNIT_WEIGHT = 1;
// Kept equal to MAX_PAGE_LIMIT in src/sampleserver/pagination.py.
const SEED_LISTING_LIMIT = 500;
const SEED_LISTING_QUERY = `?limit=${String(SEED_LISTING_LIMIT)}&offset=0`;

interface DensifiedRoute<Point extends PlanarPoint> {
    readonly targetCount: number;
    readonly weightOf: (point: Point) => number;
    /** Points laid out from the catalog's own rows, for a sandbox whose embedding has yet to run. */
    readonly seed: () => Promise<readonly Point[]>;
}

/**
 * Uncategorized samples make up most of a real library, so an uncategorized point grows a cluster
 * eight times the size of a categorized one and the recessive substrate dominates the way it does
 * there.
 */
function sampleWeight(point: CloudPoint): number {
    return point.category === UNCATEGORIZED_CATEGORY ? UNCATEGORIZED_CLUSTER_WEIGHT : UNIT_WEIGHT;
}

function moduleWeight(): number {
    return UNIT_WEIGHT;
}

/**
 * Reads one JSON body from the backend.
 *
 * Raises:
 *     Error: when the backend answers with a failing status, which the dev server reports as its own.
 */
async function readJson<Body>(path: string, backendUrl: string): Promise<Body> {
    const url = new URL(path, backendUrl);
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`densify-cloud: ${url.href} answered ${String(response.status)}`);
    }
    return (await response.json()) as Body;
}

/** The sandbox's samples as cloud points, grouped into clusters by the category each already carries. */
async function seedSamplePoints(backendUrl: string): Promise<readonly CloudPoint[]> {
    const page = await readJson<Page<SampleSummary>>(SAMPLE_LISTING_PATH + SEED_LISTING_QUERY, backendUrl);
    const placed = seedLayout(page.items, {
        keyOf: (sample) => sample.hash,
        groupOf: (sample) => sample.category,
    });
    return placed.map((sample) => ({
        sample_hash: sample.hash,
        x: sample.x,
        y: sample.y,
        category: sample.category,
        playback_rate_hz: sample.playback_rate_hz,
    }));
}

/** The sandbox's modules as cloud points, grouped into clusters by tracker format. */
async function seedModulePoints(backendUrl: string): Promise<readonly ModuleCloudPoint[]> {
    const page = await readJson<Page<ModuleSummary>>(MODULE_LISTING_PATH + SEED_LISTING_QUERY, backendUrl);
    const placed = seedLayout(page.items, {
        keyOf: (module) => module.hash,
        groupOf: (module) => module.tracker,
    });
    return placed.map((module) => ({ module_hash: module.hash, x: module.x, y: module.y }));
}

async function answerDensified<Point extends PlanarPoint>(
    pathname: string,
    route: DensifiedRoute<Point>,
    backendUrl: string,
    response: ServerResponse,
): Promise<void> {
    const upstream = await fetch(new URL(pathname, backendUrl));
    if (!upstream.ok) {
        response.statusCode = upstream.status;
        response.end(await upstream.text());
        return;
    }
    const embedded = (await upstream.json()) as readonly Point[];
    const points = embedded.length > 0 ? embedded : await route.seed();
    const densified = densifyPoints(points, {
        targetCount: route.targetCount,
        seed: DENSIFY_SEED,
        weightOf: route.weightOf,
    });
    response.setHeader("Content-Type", JSON_CONTENT_TYPE);
    response.end(JSON.stringify(densified));
}

function describeTargets(sampleTarget: number | null, moduleTarget: number | null): string {
    const parts = [
        sampleTarget === null ? null : `${SAMPLE_CLOUD_PATH} grown to ${String(sampleTarget)} points`,
        moduleTarget === null ? null : `${MODULE_CLOUD_PATH} grown to ${String(moduleTarget)} points`,
    ];
    return `densify-cloud: ${parts.filter((part) => part !== null).join(", ")}`;
}

/**
 * A dev-server middleware that answers the cloud's two point routes with the backend's own points
 * grown to the counts `VITE_CLOUD_DENSIFY` and `VITE_CLOUD_DENSIFY_MODULES` name, so the sandbox's
 * few dozen samples show the density of a real library. A catalog whose embedding has yet to run is
 * laid out from its own listing first, which keeps every point on a real hash and so keeps hovering,
 * playing and morphing reaching the catalog. Every other route, the cloud's labels and suggestions
 * included, passes on to the `/api` proxy. Vite runs plugin middlewares ahead of its proxy, which is
 * what lets this one see the request first.
 */
export function densifyCloudPlugin(options: DensifyCloudPluginOptions): Plugin {
    return {
        name: PLUGIN_NAME,
        apply: "serve",
        configureServer(server: ViteDevServer): void {
            const sampleTarget = parseDensifyTarget(options.sampleTargetText);
            const moduleTarget = parseDensifyTarget(options.moduleTargetText);
            if (sampleTarget === null && moduleTarget === null) {
                return;
            }
            server.config.logger.info(describeTargets(sampleTarget, moduleTarget));
            const handle: Connect.NextHandleFunction = (request, response, next): void => {
                const pathname = new URL(request.url ?? "/", URL_BASE).pathname;
                if (request.method !== GET_METHOD) {
                    next();
                    return;
                }
                if (pathname === SAMPLE_CLOUD_PATH && sampleTarget !== null) {
                    const route: DensifiedRoute<CloudPoint> = {
                        targetCount: sampleTarget,
                        weightOf: sampleWeight,
                        seed: () => seedSamplePoints(options.backendUrl),
                    };
                    void answerDensified(pathname, route, options.backendUrl, response).catch(next);
                    return;
                }
                if (pathname === MODULE_CLOUD_PATH && moduleTarget !== null) {
                    const route: DensifiedRoute<ModuleCloudPoint> = {
                        targetCount: moduleTarget,
                        weightOf: moduleWeight,
                        seed: () => seedModulePoints(options.backendUrl),
                    };
                    void answerDensified(pathname, route, options.backendUrl, response).catch(next);
                    return;
                }
                next();
            };
            server.middlewares.use(handle);
        },
    };
}
