import { useEffect, useState } from "react";

import { refusalDetail } from "../api/client";
import type { WaveformPeak } from "../api/samples";

const SILENT: WaveformPeak = { minimum: 0, maximum: 0 };

/** Audio as a view draws it: its contour, how long it lasts, and what the server said where it served none. */
export interface AudioReading {
    readonly peaks: readonly WaveformPeak[] | null;
    readonly seconds: number | null;
    readonly refusal: string | null;
}

const UNREAD: AudioReading = { peaks: null, seconds: null, refusal: null };

let sharedContext: AudioContext | null = null;

/** The one context the app decodes through, made on first use since a browser grants only a few. */
function decodingContext(): AudioContext | null {
    if (typeof AudioContext === "undefined") {
        return null;
    }
    sharedContext ??= new AudioContext();
    return sharedContext;
}

/** Every channel summed and averaged, which is the one amplitude a contour draws. */
function monoOf(buffer: AudioBuffer): Float32Array {
    if (buffer.numberOfChannels === 1) {
        return buffer.getChannelData(0);
    }
    const mono = new Float32Array(buffer.length);
    for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
        const data = buffer.getChannelData(channel);
        for (let index = 0; index < mono.length; index += 1) {
            mono[index] = (mono[index] ?? 0) + (data[index] ?? 0);
        }
    }
    for (let index = 0; index < mono.length; index += 1) {
        mono[index] = (mono[index] ?? 0) / buffer.numberOfChannels;
    }
    return mono;
}

/**
 * A waveform reduced to the extremes it reaches in each of `bucketCount` equal spans of its length.
 *
 * This is the reading `samplecore.waveform.compute_waveform_peaks` gives a stored thumbnail, at
 * whatever detail the caller asks for: audio shorter than the buckets asked for yields one bucket
 * per frame, so a contour claims only the detail the audio holds.
 */
export function peaksFrom(samples: Float32Array, bucketCount: number): readonly WaveformPeak[] {
    const buckets = Math.min(bucketCount, samples.length);
    const peaks: WaveformPeak[] = [];
    for (let bucket = 0; bucket < buckets; bucket += 1) {
        const from = Math.floor((bucket * samples.length) / buckets);
        const to = Math.floor(((bucket + 1) * samples.length) / buckets);
        let minimum = samples[from] ?? 0;
        let maximum = minimum;
        for (let index = from + 1; index < to; index += 1) {
            const value = samples[index] ?? 0;
            minimum = Math.min(minimum, value);
            maximum = Math.max(maximum, value);
        }
        peaks.push({ minimum, maximum });
    }
    return peaks;
}

/** The peaks scaled so the loudest of them reaches full height. Silence stands as it is, having no height to reach. */
export function normalized(peaks: readonly WaveformPeak[]): readonly WaveformPeak[] {
    const loudest = peaks.reduce(
        (highest, peak) => Math.max(highest, Math.abs(peak.minimum), Math.abs(peak.maximum)),
        0,
    );
    if (loudest === 0) {
        return peaks.map(() => SILENT);
    }
    return peaks.map((peak) => ({ minimum: peak.minimum / loudest, maximum: peak.maximum / loudest }));
}

async function read(audioUrl: string, bucketCount: number, signal: AbortSignal): Promise<AudioReading> {
    const context = decodingContext();
    if (context === null) {
        return UNREAD;
    }
    const response = await fetch(audioUrl, { signal });
    if (!response.ok) {
        const detail = await refusalDetail(response);
        return { ...UNREAD, refusal: detail ?? `the audio was answered with status ${String(response.status)}` };
    }
    const buffer = await context.decodeAudioData(await response.arrayBuffer());
    return {
        peaks: normalized(peaksFrom(monoOf(buffer), bucketCount)),
        seconds: buffer.duration,
        refusal: null,
    };
}

/**
 * Reads whatever audio stands at `audioUrl` and gives back its contour at the detail asked for,
 * its length, and the server's own words where it served none.
 *
 * Decoding in the browser draws the audio itself rather than a stored preview of it, and reads the
 * answer to the request, which is where a refusal states its reason -- neither a media element nor
 * a waveform library exposes that, so audio a server declines to serve is otherwise only silence.
 * The file is the one the browser already holds for playing it.
 */
export function useAudioPeaks(audioUrl: string | null, bucketCount: number): AudioReading {
    const [reading, setReading] = useState<AudioReading>(UNREAD);

    useEffect(() => {
        if (audioUrl === null) {
            setReading(UNREAD);
            return undefined;
        }

        let active = true;
        const request = new AbortController();
        void read(audioUrl, bucketCount, request.signal)
            .catch((): AudioReading => {
                // A request cut off, refused at the transport, or holding audio the browser cannot
                // decode leaves the view a contour short, which is all a contour can say about it.
                return UNREAD;
            })
            .then((next) => {
                if (active) {
                    setReading(next);
                }
            });

        return (): void => {
            active = false;
            request.abort();
        };
    }, [audioUrl, bucketCount]);

    return reading;
}
