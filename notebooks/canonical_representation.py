import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    from samplecore.config import ConfigurationError, load_config
    from samplecore.storage.database import connect
    from samplecore.storage.repositories.sample import PostgresSampleRepository
    from samplemorph.measurement.corpus import (
        DEFAULT_PROBE_FRAME_CEILING,
        DEFAULT_PROBE_FRAME_FLOOR,
        read_probe_samples,
    )
    from samplemorph.measurement.equivariance import (
        equivariance_trials,
        summarize_equivariance,
        unrelated_grid_distance,
    )
    from samplemorph.measurement.reconstruction import (
        ReconstructionRung,
        reconstruction_trials,
        summarize_reconstruction,
        unrelated_distance_db,
    )
    from samplemorph.registries import CANONICALIZER_REGISTRY

    return (
        CANONICALIZER_REGISTRY,
        ConfigurationError,
        DEFAULT_PROBE_FRAME_CEILING,
        DEFAULT_PROBE_FRAME_FLOOR,
        PostgresSampleRepository,
        ReconstructionRung,
        connect,
        equivariance_trials,
        load_config,
        mo,
        read_probe_samples,
        reconstruction_trials,
        summarize_equivariance,
        summarize_reconstruction,
        unrelated_distance_db,
        unrelated_grid_distance,
    )


@app.cell
def _(mo):
    mo.md(r"""
        # The canonical sound image

        Every cell here is a thin display over `samplemorph.measurement`. The trial generation, the
        distances and the summaries all live there, under their own tests. This notebook exists to
        *look at* the resulting numbers before trusting them.

        Two questions decide the frequency axis:

        1. **Translation equivariance** — reading one waveform at a different rate should leave the
           canonical grid where it was and move only the conditioners. The grid distance under
           retuning is read against the distance between two unrelated samples.
        2. **Reconstruction** — restoring an image and making it audible should land far closer to
           the original than an unrelated sample does. Splitting synthesis into a rung handed the
           source's own phase and a rung estimating it says how much the phase estimate costs.
        """)
    return


@app.cell
def _(ConfigurationError, connect, load_config):
    try:
        library_config = load_config()
        catalog_connection = connect(library_config.database_url, read_only=True)
        config_error = None
    except ConfigurationError as error:
        library_config, catalog_connection, config_error = None, None, error
    return catalog_connection, config_error, library_config


@app.cell
def _(config_error, mo):
    mo.md(f"No local config found: {config_error}") if config_error is not None else None
    return


@app.cell
def _(mo):
    probe_count = mo.ui.number(start=10, stop=400, step=10, value=60, label="Samples in the probe")
    random_seed = mo.ui.number(start=0, stop=999, step=1, value=7, label="Seed")
    return probe_count, random_seed


@app.cell
def _(catalog_connection, mo, probe_count, random_seed):
    mo.hstack([probe_count, random_seed]) if catalog_connection is not None else None
    return


@app.cell
def _(
    DEFAULT_PROBE_FRAME_CEILING,
    DEFAULT_PROBE_FRAME_FLOOR,
    PostgresSampleRepository,
    catalog_connection,
    library_config,
    probe_count,
    random_seed,
    read_probe_samples,
):
    if catalog_connection is None:
        probes = ()
    else:
        with catalog_connection.engine.connect() as session:
            drawn_samples = PostgresSampleRepository(session).sample_reproducibly(
                count=probe_count.value,
                random_seed=random_seed.value,
                frame_floor=DEFAULT_PROBE_FRAME_FLOOR,
                frame_ceiling=DEFAULT_PROBE_FRAME_CEILING,
            )
        probes = read_probe_samples(library_config.library_root, drawn_samples)
    return (probes,)


@app.cell
def _(
    CANONICALIZER_REGISTRY,
    equivariance_trials,
    probes,
    random_seed,
    summarize_equivariance,
    unrelated_grid_distance,
):
    equivariance_summaries = []
    for canonicalizer_name in sorted(CANONICALIZER_REGISTRY):
        if not probes:
            break
        axis = CANONICALIZER_REGISTRY[canonicalizer_name]()
        equivariance_summaries.append(
            summarize_equivariance(
                equivariance_trials(probes, axis),
                canonicalizer_name=canonicalizer_name,
                unrelated_distance=unrelated_grid_distance(probes, axis, random_seed=random_seed.value),
            )
        )
    return (equivariance_summaries,)


@app.cell
def _(equivariance_summaries, mo):
    equivariance_rows = [
        {
            "axis": summary.canonicalizer_name,
            "unrelated": round(summary.unrelated_grid_distance, 4),
            "under retuning": round(summary.median_grid_distance, 4),
            "explained": f"{summary.explained_share:.0%}",
            "translation error (semitones)": round(summary.median_translation_error_semitones, 2),
        }
        for summary in equivariance_summaries
    ]
    (
        mo.vstack([mo.md("## Translation equivariance"), mo.ui.table(equivariance_rows)])
        if equivariance_rows
        else mo.md("Draw a probe to measure translation equivariance.")
    )
    return


@app.cell
def _(equivariance_summaries, mo):
    offset_rows = [
        {
            "axis": summary.canonicalizer_name,
            "retuning (semitones)": offset.semitone_offset,
            "grid distance": round(offset.median_grid_distance, 4),
            "translation error": round(offset.median_translation_error_semitones, 2),
            "within half a semitone": f"{offset.exact_translation_share:.0%}",
        }
        for summary in equivariance_summaries
        for offset in summary.offsets
    ]
    (mo.vstack([mo.md("### Per retuning"), mo.ui.table(offset_rows)]) if offset_rows else None)
    return


@app.cell
def _(
    CANONICALIZER_REGISTRY,
    ReconstructionRung,
    probes,
    random_seed,
    reconstruction_trials,
    summarize_reconstruction,
    unrelated_distance_db,
):
    reconstruction_summaries = []
    for reconstruction_name in sorted(CANONICALIZER_REGISTRY):
        if not probes:
            break
        reconstruction_summaries.append(
            summarize_reconstruction(
                reconstruction_trials(probes, CANONICALIZER_REGISTRY[reconstruction_name]()),
                canonicalizer_name=reconstruction_name,
                unrelated_distance=unrelated_distance_db(probes, random_seed=random_seed.value),
            )
        )
    return (ReconstructionRung, reconstruction_summaries)


@app.cell
def _(ReconstructionRung, mo, reconstruction_summaries):
    reconstruction_rows = [
        {
            "axis": summary.canonicalizer_name,
            "unrelated (dB)": round(summary.unrelated_distance_db, 2),
            "oracle phase (dB)": round(summary.rung(ReconstructionRung.ORACLE_PHASE).median_distance_db, 2),
            "estimated phase (dB)": round(summary.rung(ReconstructionRung.ESTIMATED_PHASE).median_distance_db, 2),
            "phase estimate costs (dB)": round(summary.phase_estimate_cost_db, 2),
            "p90 (dB)": round(summary.rung(ReconstructionRung.ESTIMATED_PHASE).upper_decile_distance_db, 2),
            "worst (dB)": round(summary.rung(ReconstructionRung.ESTIMATED_PHASE).worst_distance_db, 2),
        }
        for summary in reconstruction_summaries
    ]
    (
        mo.vstack([mo.md("## Reconstruction"), mo.ui.table(reconstruction_rows)])
        if reconstruction_rows
        else mo.md("Draw a probe to measure reconstruction.")
    )
    return


if __name__ == "__main__":
    app.run()
