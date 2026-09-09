# NHS RTT Waiting Times

A trustworthy, reproducible data-ingestion and validation pipeline for monthly
NHS Referral-to-Treatment (RTT) waiting-times data.

**Development month:** June 2026 (`data/raw/rtt_2026_06.csv`) — see
`docs/decisions.md` D-001. April and May 2026 were out of scope for Phases 1–2
and enter as the first cross-month validation in Phase 3
(`docs/phase3_ingestion.md`).

## Goal

Build a pipeline that ingests raw monthly NHS RTT publications, profiles them,
validates them against documented expectations, transforms them into a clean
analytical dataset, and recomputes the headline metrics so they can be checked
against the official figures.

## Repository layout

```
data/
  raw/          Untouched source files exactly as downloaded (never edited)
  interim/      Intermediate artefacts produced by the pipeline
  processed/    Clean, analysis-ready datasets
  reference/    Lookup tables, code lists, org reference data
notebooks/      Exploratory work (01 discovery, 02 metric validation)
src/nhs_rtt/    Pipeline package (ingest, profile, validate, transform, metrics)
tests/          Unit tests
outputs/        Generated profiles, figures, tables
sql/            SQL scripts
powerbi/        Power BI assets
docs/           Charter, data dictionary, assumptions, decisions log
```

## Getting started

Phase 1 uses the pre-approved interpreter
`C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe` (Python 3.14; pandas 3.0.5,
numpy 2.5.3, pyarrow 25.0.1, pytest 9.1.x). The package is installed editable
into it so `import nhs_rtt` and the CLI resolve:

```bash
"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pip install -e .
"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pytest -q
"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m nhs_rtt.profile data/raw/rtt_2026_06.csv --outdir outputs/profiles
```

Dependency specifiers in `requirements.txt` / `pyproject.toml` are **minimum
bounds, not pins**; there is no lockfile yet.

## Pipeline stages

| Stage     | Module(s)                              | Status | Purpose |
|-----------|---------------------------------------|--------|---------|
| Profile   | `nhs_rtt.profile`                      | Phase 1 ✅ | Describe structure, types, ranges, nulls |
| Semantics | `nhs_rtt.semantics`                    | Phase 2 ✅ | Field meanings, grain, arithmetic, candidate key, exact 105-band gate |
| Ingest    | `nhs_rtt.ingest` + `nhs_rtt.crossmonth`| Phase 3 ✅ | Deterministic multi-month discovery, SHA-256 provenance, per-month acceptance, cross-month diagnostics, deterministic combine → Parquet |
| Transform | `nhs_rtt.transform`                    | Phase 4 ✅ | Verified-input gate → row-preserving analytical-wide + dense waiting-band-long + DQ/transformation report |
| Metrics   | `nhs_rtt.metrics`                      | Phase 7 | Recompute headline RTT metrics for checking |

Phase 3: `python -m nhs_rtt.ingest` (or `notebooks/03_multi_month_ingestion.ipynb`)
discovers `data/raw/rtt_YYYY_MM.csv` against the registry `data/raw/manifest.json`
(tracked), validates each month against the frozen Phase 1/2 contracts, and writes
the combined **`data/interim/rtt_combined.parquet`** (git-ignored, regenerated
from the raw set + `src/`). See `docs/phase3_ingestion.md`.

Phase 4: `python -m nhs_rtt.transform` (or `notebooks/04_transformation_analytical_dataset.ipynb`;
`--verify` checks the published set) consumes a **private immutable snapshot** of
the verified Phase 3 publication (never re-reads the raw CSVs or mutates the
Phase 3 output), and publishes to git-ignored **`data/processed/`** as one
coherent generation: `rtt_analytical_wide.parquet` (541,363 rows, row-preserving,
+ 13 derived columns), `rtt_waiting_band_long.parquet` (dense: 56,843,115 =
541,363 × 105 — validated positionally from disk before commit),
`wait_band_metadata.parquet` (105 rows), `phase4_transformation_report.{json,md}`,
and `phase4_generation.json` (commit marker binding the Phase 3 identity + every
output's SHA-256; consumer gate `transform.verify_phase4_publication`).
Missingness is preserved throughout (**no `fillna(0)`**; explicit `0` ≠ `<NA>`).
Independent audit: `docs/phase4_codex_audit.md` (PASS WITH CHANGES → remediated,
`docs/decisions.md` D-041). See `docs/phase4_transformation.md`.

## Reproducibility

- Raw data is immutable; all derived data is regenerated from `src/`.
- The June profile is reproducible: a fresh run rewrites the nine profile CSVs
  byte-for-byte (independently confirmed — `docs/phase1_audit.md`).
- Provenance captured so far (size, SHA-256) is in `docs/data_provenance.md`;
  source URL / download time / publication date are **not yet recorded**.
  Automatic capture of URLs, checksums and package versions on every run is a
  later-phase goal, not yet implemented.
- Design choices: `docs/decisions.md`. Open questions: `docs/assumptions.md`.
