import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import type { components } from "../../api/schema";
import { useSampleDetail } from "../../samples/useSampleDetail";
import { type RateOption, WaveformPlayer } from "../../samples/WaveformPlayer";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

type PlaybackRate = components["schemas"]["SamplePlaybackRate"];

interface FocusedWaveformProps {
    readonly sampleHash: string;
}

function rateOptionsFrom(playbackRates: readonly PlaybackRate[]): RateOption[] {
    return playbackRates.map((rate) => ({ rateHz: rate.rate_hz, eventCount: rate.event_count }));
}

function FocusedWaveform({ sampleHash }: FocusedWaveformProps): ReactElement {
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
        return <p className="no-selection">This sample has no rate the library is known to play it at.</p>;
    }

    const rateOptions = rateOptionsFrom(sample.playback_rates);
    const rateHz =
        selectedRateHz !== null && rateOptions.some((option) => option.rateHz === selectedRateHz)
            ? selectedRateHz
            : sample.playback_rate_hz;

    return (
        <WaveformPlayer
            sampleHash={sample.hash}
            rateHz={rateHz}
            rateOptions={rateOptions}
            onRateChange={setSelectedRateHz}
        />
    );
}

export function WaveformPanel(): ReactElement {
    const focusedSampleHash = useSelectionStore((state) => state.focusedSampleHash);

    if (focusedSampleHash === null) {
        return <p className="no-selection">No sample focused yet — double-click a sample to hear it here.</p>;
    }

    return <FocusedWaveform sampleHash={focusedSampleHash} />;
}
