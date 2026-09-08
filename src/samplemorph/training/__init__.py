from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from samplemorph.codecs import SampleCodec
from samplemorph.images import SoundImage


class CodecTrainer(Protocol):
    """Fits a codec to a body of sound images, producing one ready to encode and decode.

    Training is kept in its own package so that decoding reaches for none of the machinery fitting
    needs: the served side of this project depends on a `SampleCodec` and never on a trainer, and
    the import contracts hold that apart.
    """

    def fit(self, images: Sequence[SoundImage]) -> SampleCodec: ...
