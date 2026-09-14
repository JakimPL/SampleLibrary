from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection

from samplecore.config import LibraryConfig
from samplecore.digests import digest_of_rows
from samplelibrary.limits.scope import MemoryScope
from samplelibrary.pipeline.layout import PipelineLayout, RunPaths
from samplelibrary.pipeline.programs import ProgramResolver
from samplelibrary.pipeline.results import DIGEST_CHARACTERS
from samplelibrary.pipeline.settings import PipelineSettings

SCOPE_PREFIX = "samplelibrary"


@dataclass(frozen=True)
class PipelineContext:
    """Everything a step reads about the library it acts on and the run acting on it.

    One connection serves the whole run's reading, so every step's inputs describe the catalog as it
    stands the moment that step is decided.
    """

    config: LibraryConfig
    settings: PipelineSettings
    connection: Connection
    layout: PipelineLayout
    run: RunPaths
    resolver: ProgramResolver
    scope: MemoryScope

    @property
    def library_identity(self) -> str:
        """What tells this library from another on the same machine, which names the scopes its steps run under."""
        return digest_of_rows([(self.config.database_url, self.config.library_root.as_posix())])[:DIGEST_CHARACTERS]

    def scope_name(self, step: str) -> str:
        """The name one step's process runs under, which another run finds it still running by."""
        return f"{SCOPE_PREFIX}-{self.library_identity}-{step}"

    def artifact(self, *parts: str) -> Path:
        """A path under the library root, which is where every artifact a step builds lives."""
        return self.config.library_root.joinpath(*parts)
