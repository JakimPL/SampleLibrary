from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from samplecore.storage.cluster.embedded.binaries import PostgresProgram, program_path
from samplecore.storage.cluster.embedded.state import (
    DATA_DIRECTORY_NAME,
    LOG_FILE_NAME,
    MANAGED_DATABASE,
    MANAGED_HOST,
    MANAGED_ROLE,
    ClusterState,
    claim_port,
    cluster_directory,
    create_cluster_state,
    read_cluster_state,
    state_path,
)
from samplecore.storage.cluster.statements import create_database, database_owner
from samplecore.storage.database import connect, connect_for_curation

VERSION_FILE_NAME: Final[str] = "PG_VERSION"
CONFIGURATION_FILE_NAME: Final[str] = "postgresql.conf"
PASSWORD_FILE_NAME: Final[str] = "password.partial"
MAINTENANCE_DATABASE: Final[str] = "postgres"
SERVER_WAIT_SECONDS: Final[int] = 300
AUTHENTICATION_METHOD: Final[str] = "scram-sha-256"
ENCODING: Final[str] = "UTF8"
LOCALE: Final[str] = "C"

_logger = logging.getLogger(__name__)


class EmbeddedClusterError(Exception):
    """Raised when the managed Postgres server fails to be created, started or stopped."""


class EmbeddedCluster:
    """A library's own Postgres server, kept inside its library root and run by the application.

    The cluster listens on the loopback address alone, under one role whose password lives in the
    cluster's state file, so the library carries its database along wherever it moves.
    """

    def __init__(self, library_root: Path) -> None:
        self._library_root = library_root

    @property
    def directory(self) -> Path:
        return cluster_directory(self._library_root)

    @property
    def data_directory(self) -> Path:
        return self.directory / DATA_DIRECTORY_NAME

    @property
    def log_path(self) -> Path:
        return self.directory / LOG_FILE_NAME

    @property
    def exists(self) -> bool:
        return state_path(self._library_root).is_file() and (self.data_directory / VERSION_FILE_NAME).is_file()

    @property
    def is_running(self) -> bool:
        """Whether the cluster's server answers, which `pg_ctl status` reports by its exit status."""
        if not self.exists:
            return False
        status = subprocess.run(
            [program_path(PostgresProgram.PG_CTL), "status", "-D", self.data_directory],
            capture_output=True,
            check=False,
        )
        return status.returncode == 0

    def ensure_running(self) -> str:
        """Create the cluster where it is missing, start its server, and return the catalog's URL.

        The catalog's database and schemas are prepared on every start, which costs a few lookups on
        a cluster that holds them and completes one that stopped partway through its creation.

        Raises:
            EmbeddedClusterError: a Postgres program failed, as its output and the server log describe.
            PostgresBinariesUnavailableError: the bundled Postgres is not installed.
        """
        state = read_cluster_state(self._library_root) if self.exists else self._create()
        if not self.is_running:
            state = claim_port(self._library_root, state)
            self._start(state)
        _prepare_catalog(state)
        return state.catalog_url

    def stop(self) -> None:
        """Stop the cluster's server, letting it end its open transactions and write its data out first.

        Raises:
            EmbeddedClusterError: `pg_ctl` failed to stop the server.
        """
        if not self.is_running:
            return
        _logger.info("Stopping the library's database.")
        self._run(PostgresProgram.PG_CTL, "stop", "-D", self.data_directory, "-m", "fast", "-w")

    def _create(self) -> ClusterState:
        """Initialize the data directory under the library's role and record where the server will listen.

        The address settings are written into the cluster's own configuration file, so `pg_ctl` starts
        it the same way on every system. A failed initialization clears its partial data directory,
        which lets the next start create the cluster afresh.
        """
        _logger.info("Creating the library's database in %s.", self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        state = create_cluster_state(self._library_root)
        password_file = self.directory / PASSWORD_FILE_NAME
        password_file.write_text(state.password, encoding="utf-8")
        try:
            self._run(
                PostgresProgram.INITDB,
                "-D",
                self.data_directory,
                "-U",
                MANAGED_ROLE,
                "--pwfile",
                password_file,
                "--auth",
                AUTHENTICATION_METHOD,
                "--encoding",
                ENCODING,
                "--locale",
                LOCALE,
            )
        except EmbeddedClusterError:
            shutil.rmtree(self.data_directory, ignore_errors=True)
            raise
        finally:
            password_file.unlink()
        with (self.data_directory / CONFIGURATION_FILE_NAME).open("a", encoding="utf-8") as configuration:
            configuration.write(_server_settings())
        return state

    def _start(self, state: ClusterState) -> None:
        _logger.info("Starting the library's database on port %d.", state.port)
        self._run(
            PostgresProgram.PG_CTL,
            "start",
            "-D",
            self.data_directory,
            "-l",
            self.log_path,
            "-o",
            f"-p {state.port}",
            "-w",
            "-t",
            str(SERVER_WAIT_SECONDS),
        )

    def _run(self, program: PostgresProgram, *arguments: str | Path) -> None:
        """Run one Postgres program to its end, its output joining the server log.

        Raises:
            EmbeddedClusterError: the program ended with a failure.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("ab") as log:
            completed = subprocess.run(
                [program_path(program), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if completed.returncode != 0:
            raise EmbeddedClusterError(
                f"{program.value} failed (exit code {completed.returncode}). See {self.log_path}."
            )


def _server_settings() -> str:
    """The settings appended to a new cluster's configuration: the loopback address alone, over TCP.

    The port travels on the command line of every start, since it moves when another program takes it.
    """
    return "\n".join(
        (
            "",
            "# Written by SampleLibrary.",
            f"listen_addresses = '{MANAGED_HOST}'",
            "unix_socket_directories = ''",
            "",
        )
    )


def _prepare_catalog(state: ClusterState) -> None:
    """Create the catalog's database where it is missing, then its tables and the curation schema."""
    maintenance_url = make_url(state.catalog_url).set(database=MAINTENANCE_DATABASE)
    engine = create_engine(maintenance_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            if database_owner(connection, name=MANAGED_DATABASE) is None:
                create_database(connection, name=MANAGED_DATABASE, owner=MANAGED_ROLE)
    finally:
        engine.dispose()
    connect(state.catalog_url).close()
    connect_for_curation(state.catalog_url).close()
