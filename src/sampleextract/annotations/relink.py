from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import Connection

from samplecore.anchoring import relinked_hash
from samplecore.models.annotation import SampleAnnotation
from samplecore.storage.curation import claim_annotation_writes
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_annotation import PostgresSampleAnnotationRepository


@dataclass(frozen=True)
class RelinkSummary:
    """What one relink pass did with the annotations whose sample the catalog no longer holds.

    ``conflicting`` holds stale annotations left where they are because the sample their slot holds
    today already carries an annotation, or because another stale annotation resolves to it too;
    which decision that sample should carry is a person's call.
    """

    checked: int
    stale: int
    relinked: int
    unresolved: tuple[SampleAnnotation, ...]
    conflicting: tuple[SampleAnnotation, ...]

    @property
    def needs_a_person(self) -> bool:
        """Whether any annotation is left for a person to decide about."""
        return bool(self.unresolved or self.conflicting)


def relink_annotations(connection: Connection) -> RelinkSummary:
    """Point every annotation whose sample the catalog has lost back at the slot it was chosen from.

    A sample's hash follows from how this project hashes audio, so changing that leaves an
    annotation naming a hash the catalog knows nothing about. Each annotation also carries the
    module slot it was found in, and reading that slot's current occupant is what recovers the
    sample it meant. Annotations whose sample is still cataloged are left exactly as they are, so
    this is safe to run at any time.

    An annotation whose module or slot is gone from the catalog too comes back under
    ``unresolved``, and one whose sample already speaks for itself under ``conflicting``; both stay
    on file untouched, for a person to decide about.
    """
    repository = PostgresSampleAnnotationRepository(connection)
    with start_batch(connection):
        claim_annotation_writes(connection)
        annotations = repository.list_all()
        annotated_hashes = {annotation.sample_hash for annotation in annotations}
        cataloged = PostgresSampleRepository(connection).get_many(list(annotated_hashes))
        stale = tuple(annotation for annotation in annotations if annotation.sample_hash not in cataloged)

        resolved = [(annotation, relinked_hash(connection, annotation)) for annotation in stale]
        target_counts = Counter(target for _, target in resolved if target is not None)
        recovered: list[tuple[SampleAnnotation, str]] = []
        unresolved: list[SampleAnnotation] = []
        conflicting: list[SampleAnnotation] = []
        for annotation, target in resolved:
            if target is None:
                unresolved.append(annotation)
            elif target in annotated_hashes or target_counts[target] > 1:
                conflicting.append(annotation)
            else:
                recovered.append((annotation, target))

        repository.delete_many(tuple(annotation.sample_hash for annotation, _ in recovered))
        repository.upsert_many(
            tuple(annotation.model_copy(update={"sample_hash": target}) for annotation, target in recovered)
        )

    return RelinkSummary(
        checked=len(annotations),
        stale=len(stale),
        relinked=len(recovered),
        unresolved=tuple(unresolved),
        conflicting=tuple(conflicting),
    )
