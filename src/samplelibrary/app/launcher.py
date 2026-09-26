from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool

from samplecore.config import ConfigurationError, InferenceConfig, LibraryConfig, load_config
from samplecore.config_editing import LibraryOptions, LibrarySources, write_library_options, write_library_sources
from samplecore.models.base import FROZEN
from samplecore.paths import default_library_root
from samplecore.ports import PortUnavailableError, free_port
from samplecore.storage.cluster.embedded.binaries import PostgresBinariesUnavailableError
from samplecore.storage.cluster.embedded.server import EmbeddedCluster, EmbeddedClusterError
from samplecore.storage.database import connect
from samplecore.storage.service_roles import ServiceRole
from samplelibrary.app.instance.lock import HeldLock, LockUnavailableError, try_lock
from samplelibrary.app.instance.place import library_lock_path
from samplelibrary.app.jobs import BuildTarget, JobRunner, JobView
from samplelibrary.app.processes import ChildProcess, probe_build_device
from samplelibrary.pipeline.devices import BuildDevice
from sampleserver.app import create_app

LOGS_DIRECTORY_NAME: Final[str] = "logs"
RENDERER_LOG_NAME: Final[str] = "renderer.log"
RENDERER_NAME: Final[str] = "morph renderer"
RENDERER_HOST_OPTION: Final[str] = "--host"
RENDERER_PORT_OPTION: Final[str] = "--port"


class LibraryInUseError(Exception):
    """Raised when another application, run under another config, holds the library open."""


ACTIVATION_FAILURES: Final[tuple[type[Exception], ...]] = (
    ConfigurationError,
    EmbeddedClusterError,
    PostgresBinariesUnavailableError,
    PortUnavailableError,
    OperationalError,
    LibraryInUseError,
    LockUnavailableError,
)

_logger = logging.getLogger(__name__)


class LibraryClosedError(Exception):
    """Raised when a build or a build option is asked for before the library is open."""


class BuildInProgressError(Exception):
    """Raised when new folders are chosen while a build runs over the library the current ones opened."""


@unique
class LibraryStatus(StrEnum):
    """Where the application stands with its library: waiting for a person's choices, opening it, open, or stuck."""

    UNCONFIGURED = "unconfigured"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"


class SetupState(BaseModel):
    """What the setup pages show: the library's status, the sources chosen for it, and what went wrong if anything did.

    `build_device` stays None until the application has asked which device builds compute on.
    """

    model_config = FROZEN

    status: LibraryStatus
    config_path: str
    sources: LibrarySources | None
    options: LibraryOptions | None
    build_device: BuildDevice | None
    suggested_library_root: str
    manages_database: bool | None
    problem: str | None
    build: JobView | None


@dataclass(frozen=True)
class HeldLibrary:
    """The library an application holds open, and the lock that keeps other applications from it."""

    root: Path
    lock: HeldLock


class Launcher:
    """The application's own process: it opens the library its config file names and runs what the library needs.

    Opening a library starts its managed database where it keeps one, builds the catalog API over
    it, and starts the morph renderer beside it. A person's new choices of folders are written into
    the config file and open the library again under them.
    """

    def __init__(
        self,
        config_path: Path,
        *,
        renderer_command: tuple[str, ...],
        pipeline_command: tuple[str, ...],
        device_command: tuple[str, ...],
    ) -> None:
        self._config_path = config_path
        self._renderer_command = renderer_command
        self._device_command = device_command
        self._build_device: BuildDevice | None = None
        self._device_probe: asyncio.Task[None] | None = None
        self._builds = JobRunner(config_path=config_path, pipeline_command=pipeline_command)
        self._config: LibraryConfig | None = None
        self._catalog: FastAPI | None = None
        self._catalog_stack = AsyncExitStack()
        self._cluster: EmbeddedCluster | None = None
        self._held_library: HeldLibrary | None = None
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
            options=LibraryOptions.of(self._config) if self._config is not None else None,
            build_device=self._build_device,
            suggested_library_root=str(default_library_root()),
            manages_database=self._config.manages_database if self._config is not None else None,
            problem=self._problem,
            build=self._builds.view(),
        )

    def start(self) -> None:
        """Ask which device builds compute on, and open the library the config file names, both in the background."""
        self._device_probe = asyncio.get_running_loop().create_task(self._probe_build_device())
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

        Raises:
            BuildInProgressError: a build runs, and the config file stays as it was.
            ConfigurationError: the choices fail validation, and the config file stays as it was.
        """
        if self._builds.is_running:
            raise BuildInProgressError("Wait for the build to finish or cancel it.")
        self._config = write_library_sources(self._config_path, sources)
        self._schedule_activation(self._config)

    def choose_options(self, options: LibraryOptions) -> None:
        """Write how the library is built into the config file; the next build reads them.

        Raises:
            LibraryClosedError: no folders have been chosen yet, so no config file holds the library.
            ConfigurationError: the config file, with the options in it, fails validation.
        """
        if self._config is None:
            raise LibraryClosedError("Save your folders first.")
        self._config = write_library_options(self._config_path, options)

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
        if self._device_probe is not None:
            await asyncio.gather(self._device_probe, return_exceptions=True)
        if self._activation is not None:
            await asyncio.gather(self._activation, return_exceptions=True)
        async with self._lock:
            await self._close_library()
            if self._cluster is not None:
                await run_in_threadpool(self._cluster.stop)
                self._cluster = None
            if self._held_library is not None:
                self._held_library.lock.release()
                self._held_library = None

    async def _probe_build_device(self) -> None:
        self._build_device = await run_in_threadpool(
            probe_build_device, self._device_command, config_path=self._config_path
        )

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
        inference = _free_inference_address(config.inference)
        catalog = create_app(
            config.catalog_url(),
            config.library_root,
            inference.url,
            role=ServiceRole.CURATOR,
            frontend_directory=None,
        )
        await self._catalog_stack.enter_async_context(catalog.router.lifespan_context(catalog))
        self._catalog = catalog
        self._renderer = ChildProcess(
            RENDERER_NAME,
            (*self._renderer_command, RENDERER_HOST_OPTION, inference.host, RENDERER_PORT_OPTION, str(inference.port)),
            config_path=self._config_path,
            log_path=config.library_root / LOGS_DIRECTORY_NAME / RENDERER_LOG_NAME,
        )
        self._renderer.start()
        _logger.info("The library at %s is open.", config.library_root)

    def _prepare_database(self, config: LibraryConfig) -> None:
        """Hold the library and start its managed database, stopping the one of a library held before and letting it go.

        The catalog's tables are then brought into existence, so a library opened on an empty
        database of a person's own serves its pages at once, empty until the first scan.
        """
        previous = self._hold_library(config.library_root)
        if self._cluster is not None and (
            not config.manages_database or self._cluster.directory.parent != config.library_root
        ):
            self._cluster.stop()
            self._cluster = None
        if previous is not None:
            previous.lock.release()
        if config.manages_database:
            self._cluster = self._cluster or EmbeddedCluster(config.library_root)
            self._cluster.ensure_running()
        connect(config.catalog_url()).close()

    def _hold_library(self, library_root: Path) -> HeldLibrary | None:
        """Take the lock of ``library_root``, and return the library held before, still locked.

        One application at a time holds a library, whichever config names it, so an application run
        from a source checkout and the installed one never share a managed database, where the one
        quitting would stop it under the other. The library held before keeps its lock until its
        database has stopped.

        Raises:
            LibraryInUseError: another application holds the library.
        """
        root = library_root.resolve()
        if self._held_library is not None and self._held_library.root == root:
            return None
        lock = try_lock(library_lock_path(root))
        if lock is None:
            raise LibraryInUseError("Another SampleLibrary has this library open. Quit that one, then try again.")
        previous, self._held_library = self._held_library, HeldLibrary(root=root, lock=lock)
        return previous

    async def _close_library(self) -> None:
        if self._renderer is not None:
            await run_in_threadpool(self._renderer.stop)
            self._renderer = None
        self._catalog = None
        await self._catalog_stack.aclose()
        self._catalog_stack = AsyncExitStack()


def _free_inference_address(configured: InferenceConfig) -> InferenceConfig:
    """The address the library's renderer listens on: the configured one while its port is free, another port otherwise.

    Raises:
        PortUnavailableError: the configured host is no address of this machine.
    """
    return configured.at_port(free_port(configured.host, preferred=(configured.port,)))
