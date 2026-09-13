import type { ReactElement } from "react";

import type { SampleDetail, SampleRelation, SimilarSample } from "../api/samples";
import { formatBytes, formatDuration } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { OptionalLabel } from "../shared/OptionalLabel";
import { SpectralDistanceReadout } from "../workspace/panels/SpectralDistanceReadout";
import { AnnotationRows } from "./AnnotationRows";
import { CategoryBadge } from "./CategoryBadge";
import { SampleOccurrenceRow } from "./SampleOccurrenceRow";
import { SampleRelationRow } from "./SampleRelationRow";
import { SimilarSampleRow } from "./SimilarSampleRow";

export type DetailTab = "occurrences" | "relations" | "similar" | "cooccurrence";

interface SampleDetailViewProps {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
    readonly similar: readonly SimilarSample[];
    readonly tab: DetailTab;
    readonly onTabChange: (tab: DetailTab) => void;
}

interface DetailTabChoice {
    readonly id: DetailTab;
    readonly label: string;
}

function OccurrencesSection({ sample }: { readonly sample: SampleDetail }): ReactElement {
    return (
        <table className="mini">
            <thead>
                <tr>
                    <th>Module</th>
                    <th>Tracker</th>
                    <th>Name</th>
                    <th>Rate</th>
                    <th>Volume</th>
                    <th>Panning</th>
                    <th>Loop</th>
                </tr>
            </thead>
            <tbody>
                {sample.occurrences.map((occurrence) => (
                    <SampleOccurrenceRow
                        key={`${occurrence.module.hash}-${String(occurrence.properties.occurrence.instrument_index)}-${String(occurrence.properties.occurrence.sample_slot)}`}
                        occurrence={occurrence}
                    />
                ))}
            </tbody>
        </table>
    );
}

function RelationsSection({
    sample,
    relations,
}: {
    readonly sample: SampleDetail;
    readonly relations: readonly SampleRelation[];
}): ReactElement {
    if (relations.length === 0) {
        return <p className="placeholder-box">No relations found for this sample.</p>;
    }
    return (
        <table className="mini">
            <thead>
                <tr>
                    <th>Sample</th>
                    <th>Type</th>
                    <th>Confidence</th>
                    <th>Method</th>
                    <th>Reviewed</th>
                </tr>
            </thead>
            <tbody>
                {relations.map((relation) => (
                    <SampleRelationRow key={relation.id} relation={relation} subjectHash={sample.hash} />
                ))}
            </tbody>
        </table>
    );
}

function SimilarSection({ similar }: { readonly similar: readonly SimilarSample[] }): ReactElement {
    if (similar.length === 0) {
        return (
            <p className="placeholder-box">No spectral neighbors yet — run the embedding pipeline to populate this.</p>
        );
    }
    return (
        <table className="mini">
            <thead>
                <tr>
                    <th>Sample</th>
                    <th>Name</th>
                    <th>Category</th>
                    <th>Distance</th>
                </tr>
            </thead>
            <tbody>
                {similar.map((neighbor) => (
                    <SimilarSampleRow key={neighbor.hash} similar={neighbor} />
                ))}
            </tbody>
        </table>
    );
}

function CooccurrenceSection(): ReactElement {
    return <p className="placeholder-box">Awaits a co-occurrence analysis across the catalog.</p>;
}

/**
 * One sample in full: its name, identity and properties above, and beneath them one of four
 * listings at a time, chosen by a tab that carries its count. The tab is the caller's, so the
 * choice outlives the sample in view: a person walking a sample's neighbors keeps seeing neighbors.
 */
export function SampleDetailView({
    sample,
    relations,
    similar,
    tab,
    onTabChange,
}: SampleDetailViewProps): ReactElement {
    const choices: readonly DetailTabChoice[] = [
        { id: "occurrences", label: `Occurrences (${String(sample.occurrences.length)})` },
        { id: "relations", label: `Relations (${String(relations.length)})` },
        { id: "similar", label: `Similar (${String(similar.length)})` },
        { id: "cooccurrence", label: "Co-occurs" },
    ];

    function section(): ReactElement {
        switch (tab) {
            case "occurrences":
                return <OccurrencesSection sample={sample} />;
            case "relations":
                return <RelationsSection sample={sample} relations={relations} />;
            case "similar":
                return <SimilarSection similar={similar} />;
            case "cooccurrence":
                return <CooccurrenceSection />;
        }
    }

    return (
        <section className="detail-scroll">
            <h2>
                <OptionalLabel value={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} />
            </h2>
            <p className="hash mono cell-muted">{sample.hash}</p>
            <SpectralDistanceReadout />
            <dl className="kv">
                <dt>Category</dt>
                <dd>
                    <CategoryBadge sampleHash={sample.hash} category={sample.category} handLabel={sample.hand_label} />
                </dd>
                <AnnotationRows key={sample.hash} sample={sample} />
                <dt>Size</dt>
                <dd className="mono">{formatBytes(sample.size_bytes)}</dd>
                <dt>Duration</dt>
                <dd className="mono">{formatDuration(sample.duration_seconds)}</dd>
                <dt>Depth</dt>
                <dd className="mono">{sample.depth}-bit</dd>
                <dt>Channels</dt>
                <dd className="mono">{sample.channels}</dd>
                <dt>Frames</dt>
                <dd className="mono">{sample.frames}</dd>
            </dl>
            <div className="detail-tabs">
                {choices.map((choice) => (
                    <button
                        key={choice.id}
                        type="button"
                        aria-pressed={tab === choice.id}
                        onClick={() => {
                            onTabChange(choice.id);
                        }}
                    >
                        {choice.label}
                    </button>
                ))}
            </div>
            <div className="detail-section">{section()}</div>
        </section>
    );
}
