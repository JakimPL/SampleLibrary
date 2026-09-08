from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from samplecore.models.base import FROZEN
from samplecore.models.scalars import Index


class ModuleNoteExtraction(BaseModel):
    """A record that one module's patterns have been read for the notes they play.

    A module whose patterns name no keys at all yields no note events, so presence here is what
    tells a resumed pass the module is finished and spares it a second parse of the file.
    """

    model_config = FROZEN

    module_id: Index
    extracted_at: datetime
