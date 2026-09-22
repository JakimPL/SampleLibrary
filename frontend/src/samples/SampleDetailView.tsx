import type { ReactElement } from "react";

import type { SampleDetail, SampleRelation, SimilarSample } from "../api/samples";
import { DetailHeader } from "../shared/DetailHeader";
import { formatBytes, formatDuration } from "../shared/format";
import { UNNAMED_SAMPLE_LABEL } from "../shared/labels";
import { AnnotationRows } from "./AnnotationRows";
import { FILE_COLUMN_LABELS, SampleFileRow } from "./SampleFileRow";
import { OCCURRENCE_COLUMN_LABELS, SampleOccurrenceRow } from "./SampleOccurrenceRow";
import { RELATION_COLUMN_LABELS, SampleRelationRow } from "./SampleRelationRow";
import { SIMILAR_COLUMN_LABELS, SimilarSampleRow } from "./SimilarSampleRow";

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

function HeaderRow({ labels }: { readonly labels: Readonly<Record<string, string>> }): ReactElement {
    return (
        <tr>
            {Object.values(labels).map((label) => (
                <th key={label}>{label}</th>
            ))}
        </tr>
    );
}

function ModuleOccurrencesTable({ sample }: { readonly sample: SampleDetail }): ReactElement {
    return (
        <table className="mini">
            <thead>
                <HeaderRow labels={OCCURRENCE_COLUMN_LABELS} />
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

function SampleFilesTable({ sample }: { readonly sample: SampleDetail }): ReactElement {
    return (
        <table className="mini">
            <thead>
                <HeaderRow labels={FILE_COLUMN_LABELS} />
            </thead>
            <tbody>
                {sample.files.map((sampleFile) => (
                    <SampleFileRow
                        key={`${sampleFile.location.directory}/${sampleFile.location.relative_path}`}
                        sampleFile={sampleFile}
                    />
                ))}
            </tbody>
        </table>
    );
}

/** Every place the sample was found: the module slots holding it, then the files of sample directories. */
function OccurrencesSection({ sample }: { readonly sample: SampleDetail }): ReactElement {
    if (sample.occurrences.length === 0 && sample.files.length === 0) {
        return <p className="placeholder-box">No module or sample file holds this sample any more.</p>;
    }
    return (
        <>
            {sample.occurrences.length > 0 && <ModuleOccurrencesTable sample={sample} />}
            {sample.files.length > 0 && <SampleFilesTable sample={sample} />}
        </>
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
                <HeaderRow labels={RELATION_COLUMN_LABELS} />
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
                <HeaderRow labels={SIMILAR_COLUMN_LABELS} />
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
        { id: "occurrences", label: `Occurrences (${String(sample.occurrences.length + sample.files.length)})` },
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
            <DetailHeader name={sample.display_name} placeholder={UNNAMED_SAMPLE_LABEL} hash={sample.hash} />
            <dl className="kv">
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
