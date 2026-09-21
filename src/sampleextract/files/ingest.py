from __future__ import annotations

from sqlalchemy import Connection

from samplecore.models.sample_file import FileFingerprint, SampleFile, SampleFileLocation
from samplecore.sample_files.decoding import DecodedSampleFile
from samplecore.storage.database import start_batch
from samplecore.storage.repositories.sample import PostgresSampleRepository
from samplecore.storage.repositories.sample_file import PostgresSampleFileRepository
from samplecore.storage.repositories.thumbnail import PostgresSampleThumbnailRepository
from samplecore.waveform import compute_thumbnail


def ingest_sample_file(
    connection: Connection, *, location: SampleFileLocation, decoded: DecodedSampleFile, fingerprint: FileFingerprint
) -> SampleFile:
    """Catalog one decoded sample file in place: its sample, the sample's thumbnail, and the file itself.

    The audio stays in the file, so the content store receives nothing. The three rows land in one
    transaction, each taken in the same order every pass follows -- the sample, its thumbnail, then
    this pass's own file row -- so two passes reaching one sample through two files wait on each
    other in turn. A location already cataloged follows the file to whatever it decodes to now.
    """
    sample = decoded.sample_pcm.sample
    sample_file = SampleFile(sample_hash=sample.hash, location=location, rate=decoded.rate, fingerprint=fingerprint)
    with start_batch(connection):
        PostgresSampleRepository(connection).upsert(sample)
        PostgresSampleThumbnailRepository(connection).upsert(compute_thumbnail(sample.hash, decoded.sample_pcm.pcm))
        PostgresSampleFileRepository(connection).upsert(sample_file)
    return sample_file
