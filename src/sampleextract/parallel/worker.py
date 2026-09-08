from __future__ import annotations

from pathlib import Path
from queue import Queue

from samplecore.cli_support import open_catalog_connection
from samplecore.config import LibraryConfig
from sampleextract.progress import QueueProgress
from sampleextract.run import ExtractionSummary, run_extraction


def extract_share(config: LibraryConfig, paths: tuple[Path, ...], counts: Queue[int]) -> ExtractionSummary:
    """Cover one share of the corpus in a process of its own, reporting each module as it lands.

    The connection is opened here rather than handed in, since a catalog connection belongs to the
    process using it: every entry point in this project opens its own the same way, and the schema
    claim ``connect`` takes settles which of several starting at once creates a fresh catalog's
    tables.
    """
    with open_catalog_connection(config.database_url) as connection:
        return run_extraction(config, connection, paths, progress=QueueProgress(counts))
