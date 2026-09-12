const PITCH_BASE = 2;

/**
 * The rate a morph between two samples is heard at. Mirrors `rate_between` in
 * `samplemorph/rendering.py`: rates are pitches, so the path between two runs through their
 * logarithms, and halfway between two rates an octave apart is the octave's midpoint.
 */
export function rateBetween(firstRateHz: number, secondRateHz: number, weight: number): number {
    return PITCH_BASE ** ((1 - weight) * Math.log2(firstRateHz) + weight * Math.log2(secondRateHz));
}

/**
 * The rate to play a morph at, or `null` when either end's rate is unknown, in which case the
 * render plays as stored, the same honest reading a sample with no known rate gets.
 */
export function morphPlaybackRateHz(
    firstRateHz: number | null,
    secondRateHz: number | null,
    weight: number,
): number | null {
    return firstRateHz === null || secondRateHz === null ? null : rateBetween(firstRateHz, secondRateHz, weight);
}
