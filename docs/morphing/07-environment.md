# Standing the GPU machine up

You are building the library from scratch on a machine that already holds the tracker module
collection. The catalog and the audio store are rebuilt locally rather than copied, which also gives
us a real test of the sharded parallel extraction on a second machine — that path has only ever run
here, and exercising it is part of the job.

## The GPU, first, because it is the likeliest time sink

The card is an **RTX 5070, 12,227 MiB**. That is Blackwell, compute capability **sm_120**.

**PyTorch wheels built against CUDA 12.1 or 12.4 will not run on it.** They carry no sm_120 kernels,
and the failure is a confusing runtime error about no kernel image being available, rather than a
clean "unsupported GPU" message. Install a build against **CUDA 12.8 or newer**:

```sh
uv pip install torch --index-url https://download.pytorch.org/whl/cu128
```

Verify before writing any model code:

```python
import torch
print(torch.__version__, torch.version.cuda)
print(torch.cuda.is_available(), torch.cuda.get_device_name(0))
print(torch.cuda.get_device_capability(0))          # expect (12, 0)
print(torch.zeros(8, device="cuda").sum().item())   # expect 0.0, and no error
```

The last line is the one that matters: `torch.cuda.is_available()` returns `True` on a mismatched
build, and only an actual kernel launch surfaces the problem.

12 GB shapes what fits. A spectrogram autoencoder over 128×64 images trains comfortably at large
batch sizes. A waveform model such as RAVE fits with a reduced batch size and gradient accumulation,
which is one reason it sits late in [`04-roadmap.md`](04-roadmap.md) rather than early.

## Prerequisites

- **Python 3.12 or later**, and [uv](https://docs.astral.sh/uv/).
- **PostgreSQL 17 or later**, running locally. Docker is deliberately absent from this project's dev
  loop; install the server natively.
- **Node.js and npm**, for the frontend checks that `make check` runs.
- **`git clone --recurse-submodules`.** `trackmod` is vendored as a submodule and installed as an
  editable path dependency; a clone without it fails at `uv sync` rather than at import time.

```sh
git clone --recurse-submodules <this repository>
cd SampleLibrary
cp config.example.toml config.toml
make install
```

`make install` runs `uv sync --all-extras --all-groups`, installs the pre-commit and pre-push hooks,
and installs the frontend's npm dependencies.

### Database

One role owns three databases — the real library, the disposable sandbox, and the one the test suite
creates per-worker databases from:

```sql
CREATE ROLE samplelibrary WITH LOGIN CREATEDB PASSWORD 'samplelibrary';
CREATE DATABASE samplelibrary OWNER samplelibrary;
CREATE DATABASE samplelibrary_dev OWNER samplelibrary;
CREATE DATABASE samplelibrary_test OWNER samplelibrary;
```

The `CREATEDB` grant is what lets the test suite give each parallel worker its own database. The
`samplelibrary:samplelibrary` credential is a deliberate throwaway already written into committed
files. Each pipeline creates its own tables the first time it connects.

### `config.toml`

Gitignored, machine-specific, and it holds real local paths — keep it out of every commit.

```toml
[library]
module_source_directory = "<your module collection>"
library_root            = "<a fresh directory with at least 4 GB free>"
database_url            = "postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary"
```

`library_root` needs about **4 GB**: the content store measured 3.9 GB over 127,492 WAV objects
across 256 shard directories on the machine this was written from, averaging 33 KB each. Local disk
rather than a network share — per-epoch random access over that many small files is dominated by
filesystem overhead rather than by bytes. `SAMPLELIBRARY_DATABASE_URL` overrides `database_url` when
set, which is how the `*-dev` Makefile targets reach the sandbox.

## Verify the environment before building anything

```sh
make check
```

That runs format, lint (codespell, mypy strict, pylint, import-linter), the Python suite, and the
frontend checks. It needs `samplelibrary_test` to exist, since the suite is a real-Postgres
integration suite. A green `make check` on a fresh clone means the stack is sound and any later
failure is yours.

## Rebuilding the library

### Extraction, sharded — please actually exercise this

```sh
make extract SHARD=0/4
make extract SHARD=1/4
make extract SHARD=2/4
make extract SHARD=3/4
```

Four terminals, concurrently, all pointed at the one database. Each run takes every fourth file of
the sorted discovery, so between them they cover the collection exactly once, and striding rather
than slicing keeps the shares alike in content. `make extract` with no `SHARD` takes the whole
corpus.

Budget from **~1.08 s/module, about 2.5 hours** for a full serial parse of a corpus this size; four
shards should approach a quarter of that, bounded by disk and by the per-module write transaction.

**Report back, because this is the measurement we want:** wall clock per shard and overall, and each
run's four counts — ingested, already known, ingested by another run, failed.

**Known correct behavior, so it is not mistaken for a bug.** Around 207 module files in a collection
this size are byte-identical duplicates of another file. When two copies land in different shards,
both runs try to insert the same module hash; one wins, the other catches the integrity error,
confirms the module is now present, rolls its own transaction back, and reports it under **"ingested
by another run"**. Exactly one row results. Verified here by forcing the collision deliberately: a
four-shard parallel build produced a catalog byte-identical to a serial one — same row counts, same
module and sample hash digests, same stored objects, no leftover `.partial` files.

A repeat pass over an already-built catalog is cheap: 68 seconds across two shards for 8,701 files,
of which 8,657 were already known and 44 unparsable.

### Thumbnails

```sh
make thumbnails
```

Needed only for the web UI's waveform previews. Skip it until you want to look at the app.

### Notes — optional, expensive, memory-hungry

```sh
make notes
```

Produces roughly 29 million `note_event` rows and about 2.8 GB of database, which is 89% of the
catalog's total size. It is needed only for the free weak-label work described in
[`05-evaluation.md`](05-evaluation.md).

It needed four restarts on the original machine: the harness kills it whenever system free memory
dips, and a worst-case module materializes about 98,000 note events at once. Resumability — a marker
table plus per-module transactions — is what made that survivable, so a killed run picks up where it
stopped. With more RAM this may run clean; watch it anyway.

### Equivalence — hold off

```sh
make equivalence   # not yet
```

`detect_equivalences` reads every sample's WAV and keeps the trimmed float64 array in a dictionary
that is never evicted, so a full pass holds the decoded corpus in RAM. Its gain-variant candidate
sweep pairs samples by frame count, which degenerates toward quadratic on a corpus of tens of
thousands of short samples clustered in the same length band. Budget hours, and **over 20 GB of
RAM** — the whole catalog decoded to float64 is about 23 GB.

See the deferred entry in [`06-alternatives.md`](06-alternatives.md). Until it is redesigned to
stream, `sample_relation` stays empty, which means every sample is its own equivalence class, group
annotation reaches exactly one sample, and the near-duplicate retrieval metric in
[`05-evaluation.md`](05-evaluation.md) has no ground truth to run against. The other four metrics do
not depend on it.

## Backups

Before any pipeline run that could damage a catalog you would rather not rebuild, dump it first.
`pg_dump` lives under the PostgreSQL `bin/` directory and is usually absent from `PATH`:

```sh
pg_dump -Fc -U samplelibrary samplelibrary > <library_root>/samplelibrary.pre-<change>-<YYYYMMDD>.dump
```

The content store is separate from the database and unaffected by a catalog restore. A catalog
backup is a large commitment — the only other way back is re-running extraction over the whole
corpus. A backup covering feature vectors alone is disposable once the run it protected has been
verified, because `samplecloud` regenerates them.

## Running the app

```sh
make serve          # uvicorn on port 8000
make frontend-dev   # vite on 5173, in a second terminal
```

For frontend work against a small disposable corpus rather than the real one, the `*-dev` targets
build and serve a 30-module sandbox on port 8001 (`make library-dev`, `make extract-dev`,
`make serve-dev`, and `make reset-dev` to wipe it).

**One standing caution about that sandbox:** its samples are 40–100 ms synthetic tones built to
exercise equivalence detection. They are fine for testing that a pipeline runs and useless for
anything that has to *sound* like music. An earlier morph demo was built against them and the result
was rightly called useless. Every listening test in [`04-roadmap.md`](04-roadmap.md) uses real
samples from the real library.

## While a batch job runs

These are real local processes competing with everything else on the machine. A saturating
multi-hour pass makes the machine unpleasant to use, and one has already been killed here for
exactly that reason. Prefer to start long passes when the machine is otherwise free, and say up
front how long you expect one to take.
