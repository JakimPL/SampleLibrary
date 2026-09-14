from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import Connection

from samplecore.cli_support import load_config_or_exit
from samplecore.exit_status import ExitStatus
from samplecore.storage.database import claim_named_lock, connect
from samplelibrary.environment import STEP_LOCK_ENVIRONMENT_VARIABLE

_logger = logging.getLogger(__name__)


def hold_step_lock() -> Connection | None:
    """Take the lock the environment names for this process, answering the connection that holds it.

    A pipeline names a lock for every step it starts, and the step holds it for as long as its
    process lives, so a pipeline started again while an earlier step still runs finds the lock taken
    and leaves the step alone, on every platform and under any memory ceiling. The lock is a
    session lock on a connection of its own, which Postgres releases the moment the process ends,
    however it ends. A process the environment names no lock for takes none and answers ``None``.

    Raises:
        SystemExit: another process holds the lock the environment names.
    """
    name = os.environ.get(STEP_LOCK_ENVIRONMENT_VARIABLE)
    if not name:
        return None

    connection = connect(load_config_or_exit().database_url, read_only=True)
    if not claim_named_lock(connection, name):
        _logger.error("Ran nothing: %s is already running in another process.", name)
        sys.exit(ExitStatus.REFUSED)
    connection.commit()
    return connection
