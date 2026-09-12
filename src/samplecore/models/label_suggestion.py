from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from samplecore.models.annotation import LabelText
from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index, SampleHash


class SampleLabelSuggestion(BaseModel):
    """One tag a listening model proposes for a sample, as of one scoring's run.

    A suggestion stands apart from a hand label and from a category: it is what a pretrained model
    hears the sample as, scored against a vocabulary of prompts, and it is kept in the hand-label
    grammar so a person accepts it into their own label as it is. `rank` orders one sample's
    suggestions from the closest match, and `score` is the cosine the model read between the sound
    and the prompt. Every suggestion belongs to the experiment that scored it, so two vocabularies
    scored over one catalog stay apart and the newest one is the one a viewer sees.
    """

    model_config = FROZEN

    experiment_id: Index
    sample_hash: SampleHash
    rank: Index
    label: LabelText
    score: float
    computed_at: datetime
