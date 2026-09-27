from __future__ import annotations

import logging
import shutil
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Final

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from samplecore.models.service_role import ServiceRole
from samplecore.processes import HIDDEN_CONSOLE_FLAGS
from samplecore.storage.atomic import PRIVATE_FILE_MODE, write_bytes_atomically
from samplecore.storage.cluster.embedded.binaries import PostgresProgram, program_path
from samplecore.storage.cluster.embedded.state import (
    DATA_DIRECTORY_NAME,
    LOG_FILE_NAME,
    MANAGED_DATABASE,
    MANAGED_HOST,
    MANAGED_ROLE,
    ClusterState,
    claim_port,
    claim_service_roles,
    cluster_directory,
    create_cluster_state,
    managed_role_name,
    read_cluster_state,
    state_path,
)
from samplecore.storage.cluster.statements import (
    create_database,
    create_service_role,
    database_owner,
    role_attributes,
    set_role_password,
)
from samplecore.storage.database import connect
from samplecore.storage.service_roles import grant_service_role

VERSION_FILE_NAME: Final[str] = "PG_VERSION"
CONFIGURATION_FILE_NAME: Final[str] = "postgresql.conf"
PASSWORD_FILE_NAME: Final[str] = "password.partial"
PRIVATE_DIRECTORY_MODE: Final[int] = 0o700
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
            creationflags=HIDDEN_CONSOLE_FLAGS,
        )
        return status.returncode == 0

    def ensure_running(self, *, own_programs: bool) -> str:
        """Create the cluster where it is missing, start its server, and return the catalog's URL.

        The catalog's database and schemas are prepared on every start, which costs a few lookups on
        a cluster that holds them and completes one that stopped partway through its creation.

        A server can outlive the application that started it, and keep running after that
        installation is removed, while it loads parts of itself from its program folder as it needs
        them, a procedural language among them. With ``own_programs``, which the application holding
        the library asks for, a server running on another installation's programs is restarted on
        this one's. A command run beside that application leaves the server as it runs.

        Raises:
            EmbeddedClusterError: a Postgres program failed, as its output and the server log describe.
            PostgresBinariesUnavailableError: the bundled Postgres is not installed.
        """
        state = read_cluster_state(self._library_root) if self.exists else self._create()
        if own_programs and self.is_running and not _runs_on(state, program_path(PostgresProgram.PG_CTL).parent):
            _logger.info("Restarting the library's database, which runs on another installation's programs.")
            self.stop()
        if not self.is_running:
            state = claim_port(self._library_root, state)
            self._start(state)
        _prepare_catalog(state, library_root=self._library_root)
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
        self._claim_directory()
        state = create_cluster_state(self._library_root)
        password_file = self.directory / PASSWORD_FILE_NAME
        write_bytes_atomically(password_file, state.password.encode("utf-8"), mode=PRIVATE_FILE_MODE)
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

    def _claim_directory(self) -> None:
        """Hold the cluster's folder, with its passwords and its server log, to its owner alone."""
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(PRIVATE_DIRECTORY_MODE)

    def _run(self, program: PostgresProgram, *arguments: str | Path) -> None:
        """Run one Postgres program to its end, its output joining the server log.

        Raises:
            EmbeddedClusterError: the program ended with a failure.
        """
        self._claim_directory()
        with self.log_path.open("ab") as log:
            completed = subprocess.run(
                [program_path(program), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                creationflags=HIDDEN_CONSOLE_FLAGS,
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
            "# Written by SampleRipper.",
            f"listen_addresses = '{MANAGED_HOST}'",
            "unix_socket_directories = ''",
            "",
        )
    )


def _prepare_catalog(state: ClusterState, *, library_root: Path) -> None:
    """Create the catalog's database where it is missing, its tables and the curation schema, and its service roles.

    Each service role is created where the cluster lacks it and logs in with the password recorded
    for it, then is granted exactly what its service needs, on every start, so a table a new
    version adds is covered too.
    """
    roles = claim_service_roles(library_root)
    maintenance_url = make_url(state.catalog_url).set(database=MAINTENANCE_DATABASE)
    engine = create_engine(maintenance_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            if database_owner(connection, name=MANAGED_DATABASE) is None:
                create_database(connection, name=MANAGED_DATABASE, owner=MANAGED_ROLE)
            for service in ServiceRole:
                _claim_service_role(connection, role=managed_role_name(service), password=roles.password(service))
    finally:
        engine.dispose()
    with closing(connect(state.catalog_url)) as connection:
        for service in ServiceRole:
            grant_service_role(connection, service=service, role=managed_role_name(service))
        connection.commit()


def _runs_on(state: ClusterState, programs: Path) -> bool:
    """Whether the cluster's server runs on the programs in ``programs``, as the server itself reports its own folder."""
    maintenance_url = make_url(state.catalog_url).set(database=MAINTENANCE_DATABASE)
    engine = create_engine(maintenance_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            server_programs = connection.execute(
                text("SELECT setting FROM pg_catalog.pg_config WHERE name = 'BINDIR'")
            ).scalar_one()
    finally:
        engine.dispose()
    return Path(str(server_programs)).resolve() == programs.resolve()


def _claim_service_role(connection: Connection, *, role: str, password: str) -> None:
    """Create the role where the cluster lacks it, and have it log in with ``password`` either way."""
    if role_attributes(connection, role=role) is None:
        create_service_role(connection, role=role, password=password)
    else:
        set_role_password(connection, role=role, password=password)
