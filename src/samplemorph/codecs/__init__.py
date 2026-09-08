from __future__ import annotations

from typing import Protocol

from samplemorph.images import SampleLatent, SoundImage


class SampleCodec(Protocol):
    """Encodes a sound image's grid to a fixed-length latent and decodes one back.

    A latent is the space a morph travels through, so a codec is judged on two counts: how closely
    decoding an encoded image returns the image, and whether a point between two encoded images
    decodes to something that sounds like one instrument rather than two playing at once.

    Fitting a codec to a body of images is a `CodecTrainer`'s work, kept apart so that decoding
    reaches for none of the machinery training needs.
    """

    @property
    def latent_size(self) -> int: ...

    def encode(self, image: SoundImage) -> SampleLatent: ...

    def decode(self, latent: SampleLatent) -> SoundImage: ...
