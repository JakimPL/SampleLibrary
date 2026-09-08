# Handover: generative embeddings and sample morphing

You are picking up a line of work that has been researched but not started. This directory holds
what was learned, what was decided, what was rejected and why, so that you can begin at the design
rather than at the beginning.

## What is wanted

SampleLibrary has a sample cloud. It works, and it serves none of the three things it is wanted for.
The goals, as the user stated them:

1. Embeddings that **reasonably reflect perceptual differences** between samples.
2. Embeddings that **classify samples** — labels are yet to be created.
3. Embeddings that **allow generating a sample from an intermediate cloud point**, morphing between
   two others. "Hard, but this is our ultimate goal."

The third is the one that reshapes everything, because it needs a representation with a decoder,
and the existing one has none and can never have one.

## The design, in a paragraph

Canonicalize each sample into a fixed-size image on a log-frequency by duration-fraction grid, plus
three scalars — frequency translation in semitones, log duration, log gain — all expressed relative
to the stored waveform, since the corpus has no notion of a sample's "true" rate. On that grid a
change of playback rate is a pure translation, so a codec becomes rate-invariant by *conditioning
on* the translation rather than destroying it, which is what makes it invertible where the current
descriptor is not. A morph is then `decode(lerp(z_a, z_b, t), lerp(c_a, c_b, t))` — a convex
combination of two latents at a weight in `[0, 1]`, with the conditioners interpolated separately so
timbre can morph at constant pitch. The argument behind every part of that is in
[`02-representation.md`](02-representation.md).

## Reading order

| | |
|---|---|
| [`01-corpus.md`](01-corpus.md) | What the library actually contains, measured. Numbers you would otherwise spend a day gathering. |
| [`02-representation.md`](02-representation.md) | Why the representation has to be shaped this way. **The one to read carefully.** |
| [`03-architecture.md`](03-architecture.md) | The `samplemorph` package: protocols, registries, storage, serving, and the codebase facts that bite. |
| [`04-roadmap.md`](04-roadmap.md) | Stages, cheapest first, each with what it must beat. |
| [`05-evaluation.md`](05-evaluation.md) | The metrics, and why building them comes before building models. |
| [`06-alternatives.md`](06-alternatives.md) | Everything considered and rejected, with reasons. Read before proposing something that sounds obvious. |
| [`07-environment.md`](07-environment.md) | Standing the machine up and rebuilding the library. **Start here.** |
| [`08-prior-research.md`](08-prior-research.md) | Earlier findings, near-verbatim. Reference only. |

## The first three things to do

1. **Stand the machine up** — [`07-environment.md`](07-environment.md). Get the CUDA question out
   of the way first; the card needs a torch build against CUDA 12.8 or newer and fails confusingly
   on older wheels. Confirm `make check` is green on a fresh clone.
2. **Rebuild the library**, running extraction as four concurrent shards, and report the timings and
   counts. That path has only ever run on one machine and the project wants it exercised.
3. **Build the evaluation harness** — [`05-evaluation.md`](05-evaluation.md) — and re-measure the
   two existing descriptor backends over the full catalog. The numbers currently guiding decisions
   came from uncommitted scripts over a fifth of the library, and every later claim needs a baseline
   that can be reproduced.

Modeling starts after that. It will feel like a detour. It is not: the fastest way to waste a month
here is to train something and have no way to tell whether it is better.

## House rules, which are not negotiable

Gathered here because they are otherwise scattered, and because they have each been asked for
directly at some point.

- **Read `docs/guidelines.md` before starting each phase**, as a ritual rather than a one-time
  lookup, and **verify the result against `docs/architecture.md`** — package ownership,
  import-linter boundaries, the persistence split — before calling a phase done. Say so in the
  completion report.
- **Stop after each phase.** Report what it did, and propose the next in one sentence with a
  suggested commit message.
- **Commit messages are a single plain line, `"<Did>: <what>"`** — for example
  `Added: a constant-Q canonicalizer`. No body, no notes, no bullet list, **no co-authorship trailer
  and no AI attribution of any kind**. This has been asked for more than once.
- **Commit only when asked.**
- **American English everywhere** — identifiers, comments, docstrings, documentation. A codespell
  pre-commit hook enforces it and reads Markdown too. Names imported from a third-party package keep
  that package's own spelling.
- **Never skip hooks.** No `--no-verify`. If a hook fails, fix the cause.
- **Ask before `git stash`.** Avoid it.
- **No `gh` or `glab`** without asking; they may be tied to the wrong account.
- **`config.toml` is gitignored and holds real local paths.** It never gets committed, and its
  contents never get pasted anywhere.
- **`make check` after each phase**, and `pre-commit run --all-files` before pushing anything large.
- **Experiments stay out of the repository.** The repository holds the machinery — protocols,
  codecs, entry points, the harness, tests. Runs, metrics and checkpoints live outside it. Clean
  repository, experimental work; the two are compatible.
- **Long batch jobs make the machine unusable while they run.** Estimate the duration up front and
  prefer a moment when the machine is free.

### One deliberate exemption

`docs/guidelines.md` requires positive-voice documentation and forbids justifying a choice by
contrasting it with a rejected alternative. **These documents are exempt, by deliberate choice.**
That rule cannot reasonably apply to a research record whose subject is which ideas were rejected
and why — [`06-alternatives.md`](06-alternatives.md) would have nothing left once the negation was
stripped out. The exemption is recorded in `docs/guidelines.md` so that a later prose sweep leaves
these files alone.

The rule holds in full for everything else: code, docstrings, and `docs/architecture.md`.

## Out of scope

- **The user's hand annotations.** Labels, ratings and favorites live in the protected `curation`
  schema, outside every purge path, and no pipeline may write to or clear them. There are zero of
  them today; when they arrive they become the primary evaluation set.
- **Replacing the existing backends.** `invariant` and `librosa` stay. They become the reference a
  learned latent has to beat, which is a more useful job than the one they have now.
- **The 2D cloud as a morph control surface.** The cloud finds samples; the morph runs between two
  chosen ones. This was decided directly by the user.
- **More than two morph points**, until two points work.
