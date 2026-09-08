# data/raw

**Immutable landing zone for source files exactly as downloaded.**

Rules:

1. Never edit, rename, or reformat anything in this folder.
2. Files are named `rtt_YYYY_MM.csv`, one per publication month, stored flat in
   this folder (no per-month subfolders).
3. Record provenance for every file in `docs/data_provenance.md`:
   - source URL
   - download date/time
   - SHA-256 checksum
   - publisher and publication date (and whether original or revised)

## NHS RTT source

NHS England publishes RTT waiting-times statistics monthly at:
<https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/>

Development dataset for Phase 1: **June 2026** — `rtt_2026_06.csv` in this
folder (the brief's "April 2025" was a typo; see `docs/decisions.md` D-001).
`rtt_2026_04.csv` and `rtt_2026_05.csv` are present but out of scope for
Phase 1 and must stay untouched.

Typical files:

- Full CSV extract ("RTT-Overview-Timeseries" / provider-level zip)
- Provider and commissioner `.xls`/`.xlsx` workbooks
- Statistical press notice (PDF) — context only, not ingested

Contents of this folder are git-ignored; the folder and this README are kept.
