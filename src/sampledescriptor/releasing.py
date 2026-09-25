from __future__ import annotations

from pathlib import Path

from samplecore.hashing import file_sha256
from sampledescriptor.descriptors.learned import read_description
from sampledescriptor.pretrained import PretrainedGrid, PretrainedRelease


def release_of(model: Path, *, url: str) -> PretrainedRelease:
    """The release record of a trained descriptor published at ``url``: its bytes' digest, and the grid it reads.

    Raises:
        FileNotFoundError: no descriptor is stored at ``model``.
    """
    description = read_description(model)
    return PretrainedRelease(
        url=url,
        sha256=file_sha256(model),
        grid=PretrainedGrid(
            canonicalizer=description.canonicalizer,
            anchor=description.geometry.anchor,
            bands_per_semitone=description.bands_per_semitone,
        ),
    )
