from __future__ import annotations

from typing import Annotated, Final

from pydantic import Field, StringConstraints

SampleHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ModuleHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

Frames = Annotated[int, Field(gt=0)]
Index = Annotated[int, Field(ge=0)]
Count = Annotated[int, Field(ge=0)]
BucketCount = Annotated[int, Field(gt=0)]

MINIMUM_RATING: Final[int] = 1
MAXIMUM_RATING: Final[int] = 5

Rating = Annotated[int, Field(ge=MINIMUM_RATING, le=MAXIMUM_RATING)]
