from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplemorph.codecs import SampleCodec
from samplemorph.codecs.identity import IdentityCodec
from samplemorph.codecs.principal_components import PrincipalComponentCodec
from samplemorph.geometry import Geometry

MODELS_DIRECTORY_NAME: Final[str] = "models"
MODEL_SUFFIX: Final[str] = ".npz"
DESCRIPTION_KEY: Final[str] = "description"
IDENTITY_CODEC_NAME: Final[str] = "identity"
PRINCIPAL_COMPONENT_CODEC_NAME: Final[str] = "principal_components"


class MorphModelDescription(BaseModel):
    """What a fitted codec is, recorded beside the arrays so a file explains itself.

    The geometry travels with the model because a codec's components describe one grid shape on one
    frequency axis: a later change to the shared defaults leaves an existing file readable and
    honest about the axis it was fitted on.
    """

    model_config = FROZEN

    codec: str
    canonicalizer: str
    geometry: Geometry
    latent_size: int
    fitted_sample_count: int
    random_seed: int
    explained_variance: float | None


@dataclass(frozen=True)
class MorphModel:
    """A fitted codec together with the record of how it was fitted."""

    description: MorphModelDescription
    codec: SampleCodec


def model_path(library_root: Path, *, name: str) -> Path:
    """Where a fitted model of this name lives, beside the audio the library already keeps.

    Models sit under the configured library root rather than in the repository, which keeps a
    machine's own large artifacts together and the repository holding machinery alone.
    """
    return library_root / MODELS_DIRECTORY_NAME / f"{name}{MODEL_SUFFIX}"


def save_model(path: Path, model: MorphModel) -> None:
    """Write a fitted codec's arrays and its description into one file.

    Raises:
        ValueError: the codec is of a kind this store has no writer for.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = dict(_codec_arrays(model.codec))
    stored[DESCRIPTION_KEY] = np.array(model.description.model_dump_json())
    with path.open("wb") as handle:
        # savez names every array through **kwds, which its own stub types as the bool `allow_pickle`.
        np.savez(handle, **stored)  # type: ignore[arg-type]


def load_model(path: Path) -> MorphModel:
    """Read a fitted codec back, rebuilding it from its own recorded description.

    Raises:
        ValueError: the file names a codec kind this store has no reader for.
    """
    with np.load(path, allow_pickle=False) as stored:
        description = MorphModelDescription.model_validate_json(str(stored[DESCRIPTION_KEY]))
        match description.codec:
            case name if name == IDENTITY_CODEC_NAME:
                codec: SampleCodec = IdentityCodec(description.geometry)
            case name if name == PRINCIPAL_COMPONENT_CODEC_NAME:
                codec = PrincipalComponentCodec(
                    mean=stored["mean"],
                    components=stored["components"],
                    explained_variance_ratio=stored["explained_variance_ratio"],
                    geometry=description.geometry,
                )
            case unknown:
                raise ValueError(f"no reader is registered for a {unknown} codec")

    return MorphModel(description=description, codec=codec)


def _codec_arrays(codec: SampleCodec) -> dict[str, np.ndarray]:
    match codec:
        case IdentityCodec():
            return {}
        case PrincipalComponentCodec():
            return {
                "mean": codec.mean,
                "components": codec.components,
                "explained_variance_ratio": codec.explained_variance_ratio,
            }
        case unknown:
            raise ValueError(f"no writer is registered for a {type(unknown).__name__}")


def describe_json(description: MorphModelDescription) -> str:
    """The description as indented JSON, for a manifest a person reads."""
    return json.dumps(json.loads(description.model_dump_json()), indent=2)
