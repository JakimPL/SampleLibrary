from __future__ import annotations

from pathlib import Path

from samplecore.storage.atomic import copy_atomically, write_bytes_atomically
from sampledescriptor.descriptors.learned import read_description
from sampledescriptor.pretrained import PRETRAINED_MANIFEST_NAME, PRETRAINED_MODEL_NAME, PretrainedManifest


def bundle_descriptor(model: Path, directory: Path) -> PretrainedManifest:
    """Copy a trained descriptor into a bundle directory, with the manifest the pipeline reads its grid from.

    Raises:
        FileNotFoundError: no descriptor is stored at ``model``.
    """
    description = read_description(model)
    manifest = PretrainedManifest(
        canonicalizer=description.canonicalizer,
        anchor=description.geometry.anchor,
        bands_per_semitone=description.bands_per_semitone,
    )
    copy_atomically(model, directory / PRETRAINED_MODEL_NAME)
    write_bytes_atomically(
        directory / PRETRAINED_MANIFEST_NAME, f"{manifest.model_dump_json(indent=2)}\n".encode("utf-8")
    )
    return manifest
