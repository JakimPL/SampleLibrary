import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import dataclasses

    import marimo as mo

    from samplecore.config import ConfigurationError, load_config
    from samplecore.models.relation import RelationType
    from samplecore.storage import audio_store
    from samplecore.storage.database import connect
    from sampleextract.equivalence.calibration import (
        gain_variant_calibration_trials,
        most_marginal_relations,
        resampled_variant_calibration_trials,
        separation_gap,
        trailing_trim_calibration_trials,
    )
    from sampleextract.equivalence.scoring import GAIN_VARIANT_MINIMUM_CONFIDENCE, RESAMPLED_MINIMUM_CONFIDENCE

    return (
        ConfigurationError,
        GAIN_VARIANT_MINIMUM_CONFIDENCE,
        RESAMPLED_MINIMUM_CONFIDENCE,
        RelationType,
        audio_store,
        connect,
        dataclasses,
        gain_variant_calibration_trials,
        load_config,
        mo,
        most_marginal_relations,
        resampled_variant_calibration_trials,
        separation_gap,
        trailing_trim_calibration_trials,
    )


@app.cell
def _(mo):
    mo.md(r"""
        # Equivalence detection calibration

        Every cell here is a thin display over `sampleextract.equivalence.calibration` and
        `sampleextract.equivalence.scoring` -- the trial generation, scoring, and separation math all
        live there, under their own tests. This notebook exists to *look at* the resulting numbers
        before trusting them, not to compute anything on its own.

        A positive separation gap means every genuine match scored above every non-match, with that
        much confidence margin between them -- a single threshold in that gap cleanly tells them
        apart. Zero or negative means it can't.
        """)
    return


@app.cell
def _(mo):
    mo.md("## Gain variants (bit-depth, amplification, and the depth-and-gain compound)")
    return


@app.cell
def _(mo):
    gains_input = mo.ui.text(value="0.25, 0.5, 2.0, 4.0", label="gains to try (comma-separated)")
    gains_input
    return (gains_input,)


@app.cell
def _(GAIN_VARIANT_MINIMUM_CONFIDENCE, dataclasses, gain_variant_calibration_trials, gains_input, mo, separation_gap):
    gains = tuple(float(value) for value in gains_input.value.split(","))
    gain_trials = gain_variant_calibration_trials(gains=gains, rng_seed=1)
    gain_gap = separation_gap(gain_trials)

    mo.vstack(
        [
            mo.md(
                f"Separation gap: **{gain_gap:.4f}** "
                f"(current threshold `GAIN_VARIANT_MINIMUM_CONFIDENCE = {GAIN_VARIANT_MINIMUM_CONFIDENCE}`)"
            ),
            mo.ui.table(
                sorted((dataclasses.asdict(trial) for trial in gain_trials), key=lambda row: row["confidence"])
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(
        "## Trailing-silence trim\n\n"
        "Every value here is a genuine match -- only the length of a silent tail differs. Try a "
        "value past `MAX_TRIM_MISMATCH_FRAMES` (32 by default) to see the gap collapse to zero: "
        "that trial's length mismatch is rejected outright, which is the boundary working as "
        "designed, not a calibration problem."
    )
    return


@app.cell
def _(mo):
    trailing_frames_input = mo.ui.text(value="0, 5, 16, 32", label="trailing silent frames to try (comma-separated)")
    trailing_frames_input
    return (trailing_frames_input,)


@app.cell
def _(
    GAIN_VARIANT_MINIMUM_CONFIDENCE,
    dataclasses,
    mo,
    separation_gap,
    trailing_frames_input,
    trailing_trim_calibration_trials,
):
    trailing_frame_counts = tuple(int(value) for value in trailing_frames_input.value.split(","))
    trim_trials = trailing_trim_calibration_trials(trailing_frame_counts=trailing_frame_counts, rng_seed=2)
    trim_gap = separation_gap(trim_trials)

    mo.vstack(
        [
            mo.md(
                f"Separation gap: **{trim_gap:.4f}** "
                f"(shares `GAIN_VARIANT_MINIMUM_CONFIDENCE = {GAIN_VARIANT_MINIMUM_CONFIDENCE}` with gain variants)"
            ),
            mo.ui.table(
                sorted((dataclasses.asdict(trial) for trial in trim_trials), key=lambda row: row["confidence"])
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md("## Resampled variants (including a compound resample-and-gain case)")
    return


@app.cell
def _(mo):
    ratios_input = mo.ui.text(value="0.5, 2.0, 3.0", label="resample ratios to try (comma-separated)")
    ratios_input
    return (ratios_input,)


@app.cell
def _(
    RESAMPLED_MINIMUM_CONFIDENCE,
    dataclasses,
    mo,
    ratios_input,
    resampled_variant_calibration_trials,
    separation_gap,
):
    ratios = tuple(float(value) for value in ratios_input.value.split(","))
    resample_trials = resampled_variant_calibration_trials(ratios=ratios, rng_seed=3)
    resample_gap = separation_gap(resample_trials)

    mo.vstack(
        [
            mo.md(
                f"Separation gap: **{resample_gap:.4f}** "
                f"(current threshold `RESAMPLED_MINIMUM_CONFIDENCE = {RESAMPLED_MINIMUM_CONFIDENCE}`)"
            ),
            mo.ui.table(
                sorted((dataclasses.asdict(trial) for trial in resample_trials), key=lambda row: row["confidence"])
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
        ## The most marginal real relations

        Requires a local `config.toml` (see `config.example.toml`). Opens the catalog read-only, so
        this notebook can never write to it.
        """)
    return


@app.cell
def _(ConfigurationError, connect, load_config, mo):
    try:
        library_config = load_config()
        catalog_connection = connect(library_config.resolved_database_path, read_only=True)
        config_error = None
    except ConfigurationError as error:
        library_config, catalog_connection, config_error = None, None, error

    mo.md(f"No local config found: {config_error}") if config_error is not None else None
    return catalog_connection, library_config


@app.cell
def _(RelationType, catalog_connection, mo):
    relation_type_picker = mo.ui.dropdown(
        options=[relation_type.value for relation_type in RelationType], value=RelationType.AMPLIFICATION_VARIANT.value
    )
    relation_limit_picker = mo.ui.number(value=10, start=1, stop=200, label="how many to list")
    mo.hstack([relation_type_picker, relation_limit_picker]) if catalog_connection is not None else None
    return relation_limit_picker, relation_type_picker


@app.cell
def _(
    RelationType,
    audio_store,
    catalog_connection,
    library_config,
    mo,
    most_marginal_relations,
    relation_limit_picker,
    relation_type_picker,
):
    def _relation_row(relation: object) -> dict[str, object]:
        subject_path = audio_store.object_path(library_config.library_root, relation.subject_hash)  # type: ignore[attr-defined]
        reference_path = audio_store.object_path(library_config.library_root, relation.reference_hash)  # type: ignore[attr-defined]
        return {
            "confidence": relation.confidence,  # type: ignore[attr-defined]
            "evidence": relation.evidence,  # type: ignore[attr-defined]
            "subject": mo.audio(str(subject_path)),
            "reference": mo.audio(str(reference_path)),
        }

    if catalog_connection is not None:
        marginal_relations = most_marginal_relations(
            catalog_connection,
            relation_type=RelationType(relation_type_picker.value),
            limit=int(relation_limit_picker.value),
        )
        mo.ui.table([_relation_row(relation) for relation in marginal_relations])
    else:
        mo.md("Fill in `config.toml` to inspect the real catalog's relations here.")
    return


if __name__ == "__main__":
    app.run()
