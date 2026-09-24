from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool

from samplecore.config import ConfigurationError, LibraryConfig, default_library_root, load_config
from samplecore.config_editing import LibrarySources, write_library_sources, write_pipeline_values
from samplecore.models.base import FROZEN
from samplecore.storage.cluster.embedded.binaries import PostgresBinariesUnavailableError
from samplecore.storage.cluster.embedded.server import EmbeddedCluster, EmbeddedClusterError
from samplecore.storage.database import connect
from samplelibrary.app.jobs import BuildTarget, JobRunner, JobView
from samplelibrary.app.processes import ChildProcess
from samplelibrary.pipeline.settings import DESCRIPTOR_SOURCE_SETTING, DescriptorSource
from sampleserver.app import create_app

LOGS_DIRECTORY_NAME: Final[str] = "logs"
RENDERER_LOG_NAME: Final[str] = "renderer.log"
RENDERER_NAME: Final[str] = "morph renderer"
NEW_LIBRARY_PIPELINE_VALUES: Final[dict[str, str]] = {DESCRIPTOR_SOURCE_SETTING: DescriptorSource.PRETRAINED.value}
ACTIVATION_FAILURES: Final[tuple[type[Exception], ...]] = (
    ConfigurationError,
    EmbeddedClusterError,
    PostgresBinariesUnavailableError,
    OperationalError,
)

_logger = logging.getLogger(__name__)


class LibraryClosedError(Exception):
    """Raised when a build is asked for before the library is open."""


@unique
class LibraryStatus(StrEnum):
    """Where the application stands with its library: waiting for a person's choices, opening it, open, or stuck."""

    UNCONFIGURED = "unconfigured"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"


class SetupState(BaseModel):
    """What the setup pages show: the library's status, the sources chosen for it, and what went wrong if anything did."""

    model_config = FROZEN

    status: LibraryStatus
    config_path: str
    sources: LibrarySources | None
    suggested_library_root: str
    manages_database: bool | None
    problem: str | None
    build: JobView | None


class Launcher:
    """The application's own process: it opens the library its config file names and runs what the library needs.

    Opening a library starts its managed database where it keeps one, builds the catalog API over
    it, and starts the morph renderer beside it. A person's new choices of folders are written into
    the config file and open the library again under them.
    """

    def __init__(
        self, config_path: Path, *, renderer_command: tuple[str, ...], pipeline_command: tuple[str, ...]
    ) -> None:
        self._config_path = config_path
        self._renderer_command = renderer_command
        self._builds = JobRunner(config_path=config_path, pipeline_command=pipeline_command)
        self._config: LibraryConfig | None = None
        self._catalog: FastAPI | None = None
        self._catalog_stack = AsyncExitStack()
        self._cluster: EmbeddedCluster | None = None
        self._renderer: ChildProcess | None = None
        self._activation: asyncio.Task[None] | None = None
        self._problem: str | None = None
        self._lock = asyncio.Lock()

    @property
    def catalog(self) -> FastAPI | None:
        """The catalog API while the library is open."""
        return self._catalog

    @property
    def config(self) -> LibraryConfig | None:
        return self._config

    @property
    def config_path(self) -> Path:
        return self._config_path

    def state(self) -> SetupState:
        return SetupState(
            status=self._status(),
            config_path=str(self._config_path),
            sources=LibrarySources.of(self._config) if self._config is not None else None,
            suggested_library_root=str(default_library_root()),
            manages_database=self._config.manages_database if self._config is not None else None,
            problem=self._problem,
            build=self._builds.view(),
        )

    def start(self) -> None:
        """Open the library the config file names, in the background, where a config file is there to read."""
        if not self._config_path.is_file():
            return
        try:
            self._config = load_config(self._config_path)
        except ConfigurationError as error:
            self._problem = str(error)
            return
        self._schedule_activation(self._config)

    def choose_sources(self, sources: LibrarySources) -> None:
        """Write a person's choices into the config file and open the library under them in the background.

        A library the application creates takes the descriptor bundled with it, so building its
        cloud trains nothing.

        Raises:
            ConfigurationError: the choices fail validation, and the config file stays as it was.
        """
        creating = not self._config_path.is_file()
        self._config = write_library_sources(self._config_path, sources)
        if creating:
            write_pipeline_values(self._config_path, NEW_LIBRARY_PIPELINE_VALUES)
        self._schedule_activation(self._config)

    def build(self, target: BuildTarget) -> None:
        """Start building the open library.

        Raises:
            LibraryClosedError: the library is not open.
            JobAlreadyRunningError: a build already runs.
        """
        if self._config is None or self._catalog is None:
            raise LibraryClosedError("The library isn't open yet.")
        self._builds.start(self._config, target)

    def cancel_build(self) -> None:
        self._builds.cancel()

    async def stop(self) -> None:
        """Stop a running build, close the library, and stop the renderer and the managed database."""
        await run_in_threadpool(self._builds.stop)
        if self._activation is not None:
            await asyncio.gather(self._activation, return_exceptions=True)
        async with self._lock:
            await self._close_library()
            if self._cluster is not None:
                await run_in_threadpool(self._cluster.stop)
                self._cluster = None

    def _status(self) -> LibraryStatus:
        if self._activation is not None and not self._activation.done():
            return LibraryStatus.STARTING
        if self._catalog is not None:
            return LibraryStatus.READY
        if self._problem is not None:
            return LibraryStatus.FAILED
        return LibraryStatus.UNCONFIGURED

    def _schedule_activation(self, config: LibraryConfig) -> None:
        self._problem = None
        self._activation = asyncio.get_running_loop().create_task(self._activate(config))

    async def _activate(self, config: LibraryConfig) -> None:
        """Open the library under ``config``, recording why it failed to open where it did."""
        async with self._lock:
            await self._close_library()
            try:
                await self._open_library(config)
            except ACTIVATION_FAILURES as error:
                _logger.error("Could not open the library: %s", error)
                self._problem = str(error)
                await self._close_library()

    async def _open_library(self, config: LibraryConfig) -> None:
        await run_in_threadpool(self._prepare_database, config)
        catalog = create_app(config.catalog_url(), config.library_root, config.inference.url, frontend_directory=None)
        await self._catalog_stack.enter_async_context(catalog.router.lifespan_context(catalog))
        self._catalog = catalog
        self._renderer = ChildProcess(
            RENDERER_NAME,
            self._renderer_command,
            config_path=self._config_path,
            log_path=config.library_root / LOGS_DIRECTORY_NAME / RENDERER_LOG_NAME,
        )
        self._renderer.start()
        _logger.info("The library at %s is open.", config.library_root)

    def _prepare_database(self, config: LibraryConfig) -> None:
        """Start the library's managed database, stopping the one of a library the application held before.

        The catalog's tables are then brought into existence, so a library opened on an empty
        database of a person's own serves its pages at once, empty until the first scan.
        """
        if self._cluster is not None and (
            not config.manages_database or self._cluster.directory.parent != config.library_root
        ):
            self._cluster.stop()
            self._cluster = None
        if config.manages_database:
            self._cluster = self._cluster or EmbeddedCluster(config.library_root)
            self._cluster.ensure_running()
        connect(config.catalog_url()).close()

    async def _close_library(self) -> None:
        if self._renderer is not None:
            await run_in_threadpool(self._renderer.stop)
            self._renderer = None
        self._catalog = None
        await self._catalog_stack.aclose()
        self._catalog_stack = AsyncExitStack()
