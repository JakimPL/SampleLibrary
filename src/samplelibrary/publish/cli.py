from __future__ import annotations

import logging
import os
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import Connection
from sqlalchemy.engine import URL

from samplecloud.categories.vocabulary import INSTRUMENT_VOCABULARY
from samplecore.cli_parsing import command_parser
from samplecore.cli_support import bootstrap_cli
from samplecore.config import LibraryConfig
from samplecore.exit_status import ExitStatus
from samplecore.models.service_role import ServiceRole
from samplecore.progress import ProgressBar
from samplecore.storage.database import connect, create_schema
from samplecore.storage.service_roles import ServiceRoleRefusedError, check_service_role, grant_service_role
from samplelibrary.paths import publication_directory
from samplelibrary.publish.audio import MissingObjectsError, PublishedAudio, build_audio_tree
from samplelibrary.publish.copying import copy_table, empty_tables
from samplelibrary.publish.messages import (
    AUDIO_READY,
    MISSING_OBJECTS,
    NEXT_STEPS,
    OWN_VOCABULARY,
    PUBLISHED,
    READER_REFUSED,
)
from samplelibrary.publish.privacy import private_prefixes, publication_problems
from samplelibrary.publish.rules import catalog_tables
from samplelibrary.publish.selection import published_selection, shown_vocabulary
from samplelibrary.publish.target import (
    READER_ROLE,
    PublishRefusedError,
    claim_tables,
    prepare_reader,
    reader_password,
    record_publication,
    refuse_a_foreign_catalog,
    target_engine,
    target_url,
)

SNAPSHOT_ISOLATION: Final[str] = "REPEATABLE READ"
COPYING_LABEL: Final[str] = "Publishing the catalog"
BYTES_PER_MEGABYTE: Final[int] = 1024 * 1024

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublicationPlan:
    """What one publication writes: the query parameters its rules read, the published folders' names, and the reader's password."""

    parameters: dict[str, list[str]]
    names: tuple[str, ...]
    password: str


@dataclass(frozen=True)
class Publication:
    """Where a publication went and what it carried."""

    server: str
    sample_count: int


def main(argv: list[str], *, prog: str) -> None:
    """Publish the library to a site: its catalog to the site's database, and its audio to a folder to upload.

    The target and the reader's password come from the environment alone
    (`samplelibrary.publish.target`). Everything is read from one snapshot of the library's catalog:
    the samples to publish (`samplelibrary.publish.selection`), then their audio, gathered into
    `samplelibrary.paths.publication_directory` (`samplelibrary.publish.audio`), then every table's
    published rows (`samplelibrary.publish.rules`), written in one transaction on the target that
    commits only once no curation row and no path of this computer is in it
    (`samplelibrary.publish.privacy`). The reader is then logged in as and checked the way a site
    checks it as it starts.

    Raises:
        SystemExit: the publication is refused (3), or the store is damaged (1).
    """
    command_parser(prog=prog, description="Publish the library to a site's database, and gather its audio.").parse_args(
        argv
    )
    config = bootstrap_cli()
    try:
        url = target_url(os.environ)
        password = reader_password(os.environ)
        publication, audio = _publish(config, url=url, password=password)
        _check_reader(url, password=password)
    except PublishRefusedError as refusal:
        for problem in refusal.problems:
            _logger.error("%s", problem)
        sys.exit(ExitStatus.REFUSED)
    except MissingObjectsError as error:
        _logger.error("%s", MISSING_OBJECTS.format(count=len(error.sample_hashes), first=error.sample_hashes[0]))
        sys.exit(ExitStatus.FAILED)
    _report(publication, audio, config)


def _publish(config: LibraryConfig, *, url: URL, password: str) -> tuple[Publication, PublishedAudio]:
    directories = tuple(directory.as_posix() for directory in config.publish.sample_directories)
    names = tuple(directory.name for directory in config.publish.sample_directories)
    with closing(connect(config.catalog_url(), read_only=True)) as library:
        source = library.execution_options(isolation_level=SNAPSHOT_ISOLATION)
        _refuse_an_own_vocabulary(source)
        selection = published_selection(source, directories=directories)
        audio = build_audio_tree(
            config.library_root,
            publication_directory(config.library_root),
            module_samples=selection.module_samples,
            file_samples=selection.file_samples,
        )
        plan = PublicationPlan(
            parameters={"directories": list(directories), "names": list(names), "unreadable": list(audio.unreadable)},
            names=names,
            password=password,
        )
        engine = target_engine(url)
        try:
            with engine.connect() as target:
                refuse_a_foreign_catalog(target)
                sample_count = _write(source, target, config=config, plan=plan)
        finally:
            engine.dispose()
    return Publication(server=f"{url.host}:{url.port}", sample_count=sample_count), audio


def _write(
    source: Connection,
    target: Connection,
    *,
    config: LibraryConfig,
    plan: PublicationPlan,
) -> int:
    """Replace the target's catalog with the publication in one transaction, and return how many samples it carries.

    Raises:
        PublishRefusedError: the written catalog would carry a curation row or a path of this
            computer; the transaction is rolled back and the target stays as it was.
    """
    with target.begin():
        claim_tables(target)
        create_schema(target)
        prepare_reader(target, password=plan.password)
        grant_service_role(target, service=ServiceRole.READER, role=READER_ROLE)
        tables = catalog_tables()
        empty_tables(target, tables)
        counts: dict[str, int] = {}
        with ProgressBar(total=len(tables), label=COPYING_LABEL) as progress:
            for table in tables:
                counts[table.fullname] = copy_table(source, target, table, parameters=plan.parameters)
                progress.update(1)
        problems = publication_problems(target, prefixes=private_prefixes(config))
        if problems:
            raise PublishRefusedError(problems)
        sample_count = counts["sample"]
        record_publication(target, published_at=datetime.now(UTC), sample_count=sample_count, names=plan.names)
    return sample_count


def _refuse_an_own_vocabulary(source: Connection) -> None:
    """Insist that the categories on show were scored with the shipped vocabulary, whose wording is no one's own.

    Raises:
        PublishRefusedError: the categories on show were scored with another vocabulary.
    """
    vocabulary = shown_vocabulary(source)
    if vocabulary is not None and set(vocabulary) != set(INSTRUMENT_VOCABULARY):
        raise PublishRefusedError((OWN_VOCABULARY,))


def _check_reader(url: URL, *, password: str) -> None:
    """Log in as the reader the site connects as, and insist it reads the catalog and changes nothing.

    Raises:
        PublishRefusedError: the reader cannot log in, or holds more or less than a site needs.
    """
    reader_url = url.set(username=READER_ROLE, password=password).render_as_string(hide_password=False)
    with closing(connect(reader_url, read_only=True)) as connection:
        try:
            check_service_role(connection, ServiceRole.READER)
        except ServiceRoleRefusedError as error:
            raise PublishRefusedError(
                tuple(READER_REFUSED.format(problem=problem) for problem in error.problems)
            ) from error


def _report(publication: Publication, audio: PublishedAudio, config: LibraryConfig) -> None:
    _logger.info(
        "%s",
        PUBLISHED.format(
            samples=f"{publication.sample_count:,}", server=publication.server, unreadable=len(audio.unreadable)
        ),
    )
    _logger.info(
        "%s",
        AUDIO_READY.format(
            path=publication_directory(config.library_root),
            files=f"{audio.files:,}",
            size=f"{audio.stored_bytes / BYTES_PER_MEGABYTE:,.0f} MB",
        ),
    )
    _logger.info("%s", NEXT_STEPS)
