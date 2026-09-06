import type { ReactElement } from "react";
import { useEffect, useState } from "react";

import { useSampleDetail } from "../../samples/useSampleDetail";
import { type RateOption, WaveformPlayer } from "../../samples/WaveformPlayer";
import { ErrorNotice } from "../../shared/ErrorNotice";
import { Loading } from "../../shared/Loading";
import { useSelectionStore } from "../selectionStore";

interface FocusedWaveformProps {
    readonly sampleHash: string;
}

function rateOptionsByOccurrenceCount(rates: readonly number[]): RateOption[] {
    const occurrenceCountByRate = new Map<number, number>();
    for (const rate of rates) {
        occurrenceCountByRate.set(rate, (occurrenceCountByRate.get(rate) ?? 0) + 1);
    }

    return Array.from(occurrenceCountByRate, ([rateHz, occurrenceCount]) => ({ rateHz, occurrenceCount })).sort(
        (first, second) => first.rateHz - second.rateHz,
    );
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
    const rateOptions = rateOptionsByOccurrenceCount(
        sample.occurrences.map((occurrence) => occurrence.properties.rate),
    );
    const [firstRateOption] = rateOptions;
    if (firstRateOption === undefined) {
        return <p className="no-selection">This sample has no occurrences to play at a real tracker rate.</p>;
    }

    const defaultRateHz = sample.dominant_rate_hz ?? firstRateOption.rateHz;
    const rateHz =
        selectedRateHz !== null && rateOptions.some((option) => option.rateHz === selectedRateHz)
            ? selectedRateHz
            : defaultRateHz;

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
