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
    scored over one catalog stay apart and the one `SuggestionPromotion` names is the one a viewer sees.
    """

    model_config = FROZEN

    experiment_id: Index
    sample_hash: SampleHash
    rank: Index
    label: LabelText
    score: float
    computed_at: datetime


class SuggestionPromotion(BaseModel):
    """Which scoring the application shows, and since when.

    A scoring shows itself in the transaction that writes it, and showing an earlier one again moves
    this record alone, so the scoring on show is a decision rather than whichever id came last.
    """

    model_config = FROZEN

    experiment_id: Index
    promoted_at: datetime


class SampleFirstPick(BaseModel):
    """One sample's closest suggestion in a scoring: the three columns a view of the whole catalog paints by."""

    model_config = FROZEN

    sample_hash: SampleHash
    label: LabelText
    score: float
