from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, select

from samplecore.config import LibraryConfig
from samplecore.storage.database import claim_extraction_lock, module
from samplecore.storage.prune import PruneSummary, prune_modules
from sampleextract.corpus import CorpusOutcome
from sampleextract.parsing import FailureStage


class PruneRefused(Exception):
    """Raised when a corpus pass leaves too little certainty about which modules are gone to remove any."""


@dataclass(frozen=True)
class GoneModules:
    """The cataloged modules no file of the corpus holds any more, by hash."""

    module_hashes: frozenset[str]


def gone_modules(connection: Connection, outcome: CorpusOutcome) -> GoneModules:
    """The cataloged modules whose file the corpus pass found nowhere, once that pass is complete enough to say so.

    A module counts as present when any file the pass read hashes to it, including a file that later
    failed to parse, so only a module with no file left at all counts as gone.

    Raises:
        PruneRefused: a share stopped, a file or folder could not be read, or the pass found no module
            file at all while the catalog holds modules, as an unmounted drive leaves it.
    """
    if outcome.worker_errors:
        raise PruneRefused("a worker stopped partway, so the pass missed files it would have read")
    unreadable = [failure.path for failure in outcome.summary.failures if failure.stage is FailureStage.READ]
    if unreadable or outcome.discovery.unreadable_directories:
        named = [*outcome.discovery.unreadable_directories, *unreadable]
        raise PruneRefused(f"{len(named)} file(s) or folder(s) could not be read, among them {named[0]}")

    cataloged = frozenset(str(row.hash) for row in connection.execute(select(module.c.hash)))
    if not outcome.discovery.paths and cataloged:
        raise PruneRefused("the source directory holds no module file while the catalog holds modules")
    return GoneModules(module_hashes=cataloged - outcome.summary.present_module_hashes)


def prune_gone_modules(config: LibraryConfig, connection: Connection, outcome: CorpusOutcome) -> PruneSummary:
    """Remove the modules whose files are gone, and the samples no remaining module holds.

    Raises:
        PruneRefused: the pass leaves the gone modules uncertain (see ``gone_modules``), or another
            extraction or note-reading pass is running on the same catalog.
    """
    gone = gone_modules(connection, outcome)
    if not claim_extraction_lock(connection):
        raise PruneRefused("another extraction or note-reading pass is running on this catalog")
    return prune_modules(connection, config.library_root, module_hashes=gone.module_hashes)
