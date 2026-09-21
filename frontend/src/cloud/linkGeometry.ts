export type ScreenPoint = readonly [number, number];

/**
 * The part of the segment from `first` to `second` left once `firstInset` is cut from its start and
 * `secondInset` from its end, so a line meets the markers at its ends at their edges; null when the
 * two cuts meet or overlap, which leaves nothing to draw.
 */
export function insetSegment(
    first: ScreenPoint,
    second: ScreenPoint,
    firstInset: number,
    secondInset: number,
): readonly [ScreenPoint, ScreenPoint] | null {
    const alongX = second[0] - first[0];
    const alongY = second[1] - first[1];
    const length = Math.hypot(alongX, alongY);
    if (length <= firstInset + secondInset) {
        return null;
    }
    const unitX = alongX / length;
    const unitY = alongY / length;
    return [
        [first[0] + unitX * firstInset, first[1] + unitY * firstInset],
        [second[0] - unitX * secondInset, second[1] - unitY * secondInset],
    ];
}

/** The screen point a fraction `t` of the way from `first` to `second`. */
export function pointAlong(first: ScreenPoint, second: ScreenPoint, t: number): ScreenPoint {
    return [first[0] + (second[0] - first[0]) * t, first[1] + (second[1] - first[1]) * t];
}

/**
 * Where along the segment from `first` to `second` a screen point falls, as a fraction held to the
 * unit interval: the point's projection onto the segment, so dragging beside the line still reads
 * as a position along it. Two coincident ends put every point at the start.
 */
export function projectWeight(first: ScreenPoint, second: ScreenPoint, point: ScreenPoint): number {
    const alongX = second[0] - first[0];
    const alongY = second[1] - first[1];
    const lengthSquared = alongX * alongX + alongY * alongY;
    if (lengthSquared === 0) {
        return 0;
    }
    const projected = ((point[0] - first[0]) * alongX + (point[1] - first[1]) * alongY) / lengthSquared;
    return Math.min(1, Math.max(0, projected));
}
