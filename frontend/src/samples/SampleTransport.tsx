import type { ReactElement } from "react";
import { useState } from "react";

import type { SampleDetail } from "../api/samples";
import type { components } from "../api/schema";
import { ErrorNotice } from "../shared/ErrorNotice";
import { fileNameStem, shortHash } from "../shared/format";
import { Loading } from "../shared/Loading";
import { useSampleDetail } from "./useSampleDetail";
import { type RateOption, WaveformPlayer } from "./WaveformPlayer";

type PlaybackRate = components["schemas"]["SamplePlaybackRate"];

const WAV_EXTENSION = ".wav";
const NO_RATE_NOTICE = "This sample has no rate the library is known to play it at.";

interface SampleTransportProps {
    readonly sample: SampleDetail;
}

interface FocusedSampleTransportProps {
    readonly sampleHash: string;
}

function rateOptionsFrom(playbackRates: readonly PlaybackRate[]): RateOption[] {
    return playbackRates.map((rate) => ({ rateHz: rate.rate_hz, eventCount: rate.event_count }));
}

/**
 * The full player of one loaded sample, at the rate the library plays it and at any other rate
 * the library has played it. A caller keys it by the sample's hash, so the rate chosen here starts
 * over with another sample.
 */
export function SampleTransport({ sample }: SampleTransportProps): ReactElement {
    const [selectedRateHz, setSelectedRateHz] = useState<number | null>(null);

    if (sample.playback_rate_hz === null) {
        return <p className="no-selection">{NO_RATE_NOTICE}</p>;
    }

    const rateOptions = rateOptionsFrom(sample.playback_rates);
    const rateHz =
        selectedRateHz !== null && rateOptions.some((option) => option.rateHz === selectedRateHz)
            ? selectedRateHz
            : sample.playback_rate_hz;

    return (
        <WaveformPlayer
            sampleHash={sample.hash}
            fileName={`${fileNameStem(sample.display_name, shortHash(sample.hash))}${WAV_EXTENSION}`}
            rateHz={rateHz}
            rateOptions={rateOptions}
            onRateChange={setSelectedRateHz}
        />
    );
}

/** The same player for a sample known by its hash alone, read through the detail request the Sample Detail shares. */
export function FocusedSampleTransport({ sampleHash }: FocusedSampleTransportProps): ReactElement {
    const state = useSampleDetail(sampleHash);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }
    return <SampleTransport key={sampleHash} sample={state.data.sample} />;
}
