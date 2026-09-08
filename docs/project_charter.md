# Project charter — NHS RTT Waiting Times

## Objective

Build a reproducible, auditable analytical pipeline for NHS England
Referral-to-Treatment (RTT) waiting-time data, and use it to investigate
variation across providers, specialties, pathway types, and time.

## Scope of Phase 1 (this work)

Data discovery, structural profiling, and repository setup **only**. No cleaning,
transformation, metric recomputation, SQL modelling, BI, or forecasting.

## Development period

- The brief first named **April 2025**; the corrected instruction is to work
  a single supplied file, **June 2026** (`data/raw/rtt_2026_06.csv`).
- Phase 1 uses **`rtt_2026_06.csv` (June 2026)** as the sole development
  dataset. See `docs/decisions.md` D-001.
- `rtt_2026_04.csv` and `rtt_2026_05.csv` are also present in `data/raw/` but
  are **not** profiled or analysed in Phase 1.

## Initial analytical questions

1. How many reporting providers are present, and are they all NHS trusts?
2. What RTT pathway categories (RTT Part Types) are reported?
3. What treatment functions are reported, and which rows are subtotals?
4. How are waiting-time distributions represented across the week buckets?
5. How do `Total`, `Total All`, and "unknown clock start" fields relate?
6. Can published NHS headline metrics be reproduced from the raw data?
7. Does the schema stay consistent across monthly publications?

## Longer-term questions (out of scope for Phase 1)

- How have waiting lists changed over time?
- Which providers and specialties contribute most to long waits?
- What proportion of incomplete pathways exceed 18 and 52 weeks?
- How does performance vary geographically?

## Principles

- Raw data under `data/raw/` is **immutable**: never edited, resaved, filtered,
  or imputed.
- All derived artefacts are regenerated from `src/nhs_rtt/`.
- Reusable logic lives in `src/nhs_rtt/`; notebooks only call it.
- Ambiguities are **documented** (`docs/assumptions.md`), not guessed.
- Design choices are logged (`docs/decisions.md`).
