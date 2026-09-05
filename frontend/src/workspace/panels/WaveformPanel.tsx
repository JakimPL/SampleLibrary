import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { useSampleDetail } from "../../samples/useSampleDetail";
import { WaveformPlayer } from "../../samples/WaveformPlayer";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

interface FocusedWaveformProps {
    readonly sampleHash: string;
}

function dedupedSortedRates(rates: readonly number[]): number[] {
    return Array.from(new Set(rates)).sort((first, second) => first - second);
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
    const rateOptions = dedupedSortedRates(sample.occurrences.map((occurrence) => occurrence.properties.rate));
    const [firstRateOption] = rateOptions;
    if (firstRateOption === undefined) {
        return <p className="no-selection">This sample has no occurrences to play at a real tracker rate.</p>;
    }

    const defaultRateHz = sample.dominant_rate_hz ?? firstRateOption;
    const rateHz = selectedRateHz !== null && rateOptions.includes(selectedRateHz) ? selectedRateHz : defaultRateHz;

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
