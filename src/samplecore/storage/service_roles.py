from __future__ import annotations

from enum import StrEnum, unique


@unique
class ServiceRole(StrEnum):
    """What a served catalog API may do to the library: read it, or read it and record a person's labels.

    A deployed site reads alone. The application a person runs on their own computer curates, and
    records labels for that person alone.
    """

    READER = "reader"
    CURATOR = "curator"

    @property
    def offers_label_editing(self) -> bool:
        return self is ServiceRole.CURATOR
