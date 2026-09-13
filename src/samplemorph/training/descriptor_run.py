from __future__ import annotations

import torch

from samplecore.labeling.ranking import agreement_matrix
from samplemorph.descriptors.grid_descriptor import DescriptorShape
from samplemorph.descriptors.learned import descriptor_path
from samplemorph.training.descriptor_data import DescriptorCorpus, DescriptorDataModule
from samplemorph.training.descriptor_export import DescriptorWriter
from samplemorph.training.descriptor_module import DescriptorTrainingModule, TeachingMaterial
from samplemorph.training.descriptor_settings import DescriptorTrainingSettings
from samplemorph.training.export import BestEpochExport
from samplemorph.training.metrics import DESCRIPTOR_MONITORED_METRIC
from samplemorph.training.runs import RunPlacement, TrainingOutcome, begin_cached_run, fit_and_export


def run_descriptor_training(
    corpus: DescriptorCorpus,
    *,
    settings: DescriptorTrainingSettings,
    placement: RunPlacement,
) -> TrainingOutcome:
    """Teach a descriptor over a cached corpus, writing what it learns as it learns it.

    What the run was asked to do reaches the record before the first epoch, together with which
    cache and which teacher it read, so a pass that ends badly is still identifiable.
    """
    begin_cached_run(
        placement,
        settings=settings.run,
        parameters=settings.as_parameters()
        | {"teacher_experiment_id": str(corpus.teacher_experiment_id), "labeled_sample_count": str(len(corpus.labels))},
        cache=corpus.cache,
    )
    data = DescriptorDataModule(corpus, settings=settings)
    module = DescriptorTrainingModule(
        DescriptorShape(
            band_count=corpus.cache.description.band_count,
            time_columns=corpus.cache.description.time_columns,
            width=settings.width,
        ),
        learning_rate=settings.run.learning_rate,
        weights=settings.weights,
        material=teaching_material(corpus),
    )
    path = descriptor_path(corpus.library_root, name=placement.model_name)
    export = BestEpochExport(
        path=path,
        monitored=DESCRIPTOR_MONITORED_METRIC,
        tracker=placement.tracker,
        writer=DescriptorWriter(module, path, corpus, data.training_sample_count),
    )
    return fit_and_export(module, data, export=export, settings=settings.run, placement=placement)


def teaching_material(corpus: DescriptorCorpus) -> TeachingMaterial:
    """The corpus's targets as tensors the module keeps on its device."""
    return TeachingMaterial(
        teacher=torch.from_numpy(corpus.teacher),
        label_position=torch.from_numpy(corpus.label_position),
        held_out=torch.from_numpy(corpus.held_out_labels),
        agreements=torch.from_numpy(agreement_matrix(corpus.labels)).float(),
    )
