from __future__ import annotations

from typing import Final

# What `sampleripper publish` tells the person publishing, each a sentence of its own.

NO_TARGET: Final[str] = (
    "Name the database to publish to in SAMPLERIPPER_PUBLISH_DATABASE_URL, such as the public URL of the "
    "site's Postgres, with a role that may create roles and tables there."
)
UNKNOWN_DRIVER: Final[str] = (
    "SAMPLERIPPER_PUBLISH_DATABASE_URL names a database this project does not connect to: {name}."
)
SERVER_IN_SETTINGS: Final[str] = (
    "SAMPLERIPPER_PUBLISH_DATABASE_URL names its server in a {name}= setting. Name the server in the "
    "address itself, before the database's name."
)
WEAK_TRANSPORT: Final[str] = (
    "A publication reaches {host} over the internet, which needs sslmode=require or stricter, not {mode}."
)
NO_READER_PASSWORD: Final[str] = (
    "Name the site's reader password in SAMPLERIPPER_PUBLISH_READER_PASSWORD, the one its "
    "SAMPLERIPPER_SERVER_DATABASE_URL holds."
)
WEAK_READER_PASSWORD: Final[str] = "The reader's password is shorter than {length} characters. Give it a generated one."
NOT_A_PUBLICATION: Final[str] = (
    "The database to publish to already holds a catalog that no publication wrote. Publishing replaces "
    "everything in it, so name an empty database, or the one a publication wrote before."
)
OWN_VOCABULARY: Final[str] = (
    "The categories on show were scored with a vocabulary of your own, which may carry your labels' wording. "
    "Score them with the shipped one before publishing: sampleripper cloud categorize --vocabulary instruments."
)
MISSING_OBJECTS: Final[str] = (
    "{count} samples a module holds have no stored audio, beginning with {first}. The library's store is "
    "damaged; extract the modules again before publishing."
)
CURATION_REACHED: Final[str] = "The publication would carry rows of {table}, which stays home. Nothing was published."
PRIVATE_VALUE: Final[str] = (
    "{table}.{column} holds a path on this computer, which a site never shows. Nothing was published."
)
READER_REFUSED: Final[str] = "The site's reader can't log in as a site needs: {problem}"
PUBLISHED: Final[str] = "Published {samples} samples to {server}, {unreadable} left out whose files could not be read."
AUDIO_READY: Final[str] = "The site's audio store is {path}: {files} files, {size}."
NEXT_STEPS: Final[str] = (
    "Next: turn off the database's TCP Proxy, redeploy the site, and upload that folder's objects to the "
    "site's volume if your samples changed. docs/deploying.md shows the commands."
)
