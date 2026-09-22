import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import type { components } from "../../api/schema";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { type RateOption, WaveformPlayer, type WaveformPlayerLayout } from "../../samples/WaveformPlayer";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { fileNameStem, shortHash } from "../../shared/format";
import { Loading } from "../../shared/Loading";

type PlaybackRate = components["schemas"]["SamplePlaybackRate"];

const WAV_EXTENSION = ".wav";
const NO_RATE_NOTICE = "This sample has no rate the library is known to play it at.";

interface FocusedSampleTransportProps {
    readonly sampleHash: string;
    readonly layout: WaveformPlayerLayout;
}

function rateOptionsFrom(playbackRates: readonly PlaybackRate[]): RateOption[] {
    return playbackRates.map((rate) => ({ rateHz: rate.rate_hz, eventCount: rate.event_count }));
}

/**
 * The full player of one sample by hash, at the rate the library plays it and at any other rate
 * the library has played it, sharing the sample's one detail request with the Sample Detail panel.
 */
export function FocusedSampleTransport({ sampleHash, layout }: FocusedSampleTransportProps): ReactElement {
    const state = useSampleDetail(sampleHash);
    const [selectedRateHz, setSelectedRateHz] = useState<number | null>(null);

    useEffect(() => {
        setSelectedRateHz(null);
    }, [sampleHash]);

    if (state.status === "loading") {
        return <Loading />;
    }
    if (state.status === "error") {
        return <ErrorNotice message={state.message} />;
    }

    const { sample } = state.data;
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
            layout={layout}
        />
    );
}
