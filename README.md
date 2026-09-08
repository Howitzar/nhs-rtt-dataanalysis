# NHS RTT Waiting Times

A trustworthy, reproducible data-ingestion and validation pipeline for monthly
NHS Referral-to-Treatment (RTT) waiting-times data.

**Development month:** June 2026 (`data/raw/rtt_2026_06.csv`) — see
`docs/decisions.md` D-001. April/May 2026 files exist but are out of scope for
Phase 1.

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

| Stage     | Module                  | Purpose                                        |
|-----------|-------------------------|------------------------------------------------|
| Ingest    | `nhs_rtt.ingest`        | Locate, download, checksum, and load raw files |
| Profile   | `nhs_rtt.profile`       | Describe structure, types, ranges, nulls       |
| Validate  | `nhs_rtt.validate`      | Assert documented expectations, flag breaches  |
| Transform | `nhs_rtt.transform`     | Reshape to tidy analytical form                |
| Metrics   | `nhs_rtt.metrics`       | Recompute headline RTT metrics for checking    |

## Reproducibility

- Raw data is immutable; all derived data is regenerated from `src/`.
- The June profile is reproducible: a fresh run rewrites the nine profile CSVs
  byte-for-byte (independently confirmed — `docs/phase1_audit.md`).
- Provenance captured so far (size, SHA-256) is in `docs/data_provenance.md`;
  source URL / download time / publication date are **not yet recorded**.
  Automatic capture of URLs, checksums and package versions on every run is a
  later-phase goal, not yet implemented.
- Design choices: `docs/decisions.md`. Open questions: `docs/assumptions.md`.
