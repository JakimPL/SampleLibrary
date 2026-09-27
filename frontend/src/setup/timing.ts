import { useEffect, useState } from "react";

import type { ProgressReport } from "../api/setup";

/** How long a pass runs before its pace is steady enough to estimate from. */
export const ESTIMATE_WARMUP_SECONDS = 10;
const CLOCK_TICK_MS = 1000;
const MILLISECONDS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;
/** Estimates round to whole minutes below the first bound, to five below the second, and to ten above it. */
const ESTIMATE_ROUNDING: readonly { readonly below: number; readonly step: number }[] = [
    { below: 10, step: 1 },
    { below: MINUTES_PER_HOUR, step: 5 },
    { below: Number.POSITIVE_INFINITY, step: 10 },
];

export function secondsBetween(start: string, end: string | number): number {
    const endMs = typeof end === "number" ? end : Date.parse(end);
    return (endMs - Date.parse(start)) / MILLISECONDS_PER_SECOND;
}

/**
 * The seconds a pass has left at the pace it has kept since it started, once it has run long
 * enough for that pace to hold; null before then and once every item is done. A pass taking up
 * where a stopped one left off keeps its pace over the items it finished itself.
 */
export function estimateRemainingSeconds(report: ProgressReport): number | null {
    const elapsed = secondsBetween(report.started_at, report.updated_at);
    const finishedHere = report.done - report.resumed;
    if (finishedHere <= 0 || report.done >= report.total || elapsed < ESTIMATE_WARMUP_SECONDS) {
        return null;
    }
    return (elapsed / finishedHere) * (report.total - report.done);
}

function describeMinutes(totalMinutes: number): string {
    const hours = Math.floor(totalMinutes / MINUTES_PER_HOUR);
    const minutes = totalMinutes % MINUTES_PER_HOUR;
    if (hours === 0) {
        return `${String(minutes)} min`;
    }
    return minutes === 0 ? `${String(hours)} h` : `${String(hours)} h ${String(minutes)} min`;
}

/** An estimate as a person reads it, rounded more coarsely the longer it is: "about 25 min left". */
export function describeEstimate(seconds: number): string {
    if (seconds < SECONDS_PER_MINUTE) {
        return "less than a minute left";
    }
    const minutes = seconds / SECONDS_PER_MINUTE;
    const step = ESTIMATE_ROUNDING.find((rounding) => minutes < rounding.below)?.step ?? 1;
    return `about ${describeMinutes(Math.round(minutes / step) * step)} left`;
}

/** A measured span: seconds under a minute, whole minutes and hours above it. */
export function describeElapsed(seconds: number): string {
    if (seconds < SECONDS_PER_MINUTE) {
        return `${String(Math.max(0, Math.floor(seconds)))} s`;
    }
    return describeMinutes(Math.floor(seconds / SECONDS_PER_MINUTE));
}

/** The current time, advancing every second while `running` holds, so running counters move between polls. */
export function useClock(running: boolean): number {
    const [now, setNow] = useState(() => Date.now());

    useEffect(() => {
        if (!running) {
            return undefined;
        }
        setNow(Date.now());
        const timer = window.setInterval(() => {
            setNow(Date.now());
        }, CLOCK_TICK_MS);
        return (): void => {
            window.clearInterval(timer);
        };
    }, [running]);

    return now;
}
