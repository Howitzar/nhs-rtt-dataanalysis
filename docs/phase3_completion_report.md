# Phase 3 Completion Report — Reproducible Multi-Month Ingestion & Provenance

> **SUPERSEDED IN PART (2026-09-08).** This report describes the *original*
> Phase 3 submission. The independent Codex audit
> (`docs/phase3_codex_audit.md`) returned **PASS WITH CHANGES** (P3-A01…A07);
> remediation is in `docs/phase3_remediation_report.md`, and
> `docs/phase3_ingestion.md` §7–§11 is the current authority. Sections below
> that describe acceptance / publication guarantees have been strengthened; the
> real-data results (541,363 rows, hashes, diagnostics, P2-U7 instances) are
> unchanged.

**Date:** 2026-09-08 · **Prepared by:** Claude Code (implementation engineer)
**Status:** original submission — audited PASS WITH CHANGES, then remediated.
Not committed, tagged or pushed. No Phase 3 Git milestone created.

Companion documents: `docs/phase3_ingestion.md` (architecture / methodology),
`docs/decisions.md` D-031…D-037, `docs/assumptions.md` (P2-U3 / P2-U5 / P2-U7),
`docs/data_provenance.md`.

---

## 1. Repository state

| | |
|---|---|
| Starting commit | `8f321473d286766d23ea4a3172b8f5b4d8e0e018` (`8f32147`), branch `main`, tag `phase-2-pass` — unchanged |
| Working-tree status | modified, **uncommitted** |
| Raw NHS CSVs | **untouched** — April/May/June SHA-256 re-verified identical to the frozen values |
| Phase 1/2 code, notebooks, tests | **not modified** (`profile.py`, `semantics.py`, `test_profile.py`, `test_semantics.py`, `notebooks/01`, `notebooks/02`) |

### Files added

| Path | Lines | Purpose |
|---|---|---|
| `src/nhs_rtt/ingest.py` | 626 | deterministic discovery, SHA-256 + registry provenance, `Period` validation, per-month acceptance gate |
| `src/nhs_rtt/crossmonth.py` | 535 | cross-month diagnostics, deterministic combine, CSV→Parquet publication |
| `tests/test_ingest.py` | 356 | 55 synthetic/adversarial tests |
| `tests/test_crossmonth.py` | 269 | 17 synthetic/adversarial tests |
| `data/raw/manifest.json` | — | **tracked** source registry (intended source set; 3 seeded entries) |
| `notebooks/03_multi_month_ingestion.ipynb` | — | thin orchestration / narrative over `src/` |
| `docs/phase3_ingestion.md` | — | dedicated Phase 3 architecture / methodology doc |
| `docs/phase3_completion_report.md` | — | this report |

### Files modified

`.gitignore` (adds only `!data/raw/manifest.json`), `README.md` (pipeline-stage
table + Phase 3 note), `docs/decisions.md` (D-031…D-037),
`docs/assumptions.md` (P2-U3 / P2-U5 marked addressed; P2-U7 carried with the
new May instance), `docs/data_provenance.md` (April + May rows; manifest
pointer).

### Ignored / generated artifacts

`data/interim/rtt_combined.parquet` (~19 MB) and
`data/interim/rtt_combined.ingest_manifest.json` — git-ignored via
`data/interim/*`, regenerated from the accepted raw set + `src/`. No raw CSV,
virtual env, cache, or executed-notebook copy is staged or committable. The only
tracked exception under `data/raw/` is `manifest.json`.

---

## 2. Implementation

### Ingestion architecture

Two modules, one-way import (`crossmonth` → `ingest`; `ingest.main()` reaches
`crossmonth` only lazily — no cycle). CLI entry point `python -m nhs_rtt.ingest`
delegates to `crossmonth.run_phase3`. No new dependencies (`pandas` + `pyarrow`
already declared). The frozen Phase 1/2 contracts are **reused, not
re-implemented**: `semantics.validate_extract` (exact 105-band schema),
`semantics.load_rtt_csv` (blank-preserving, negatives rejected),
`semantics.candidate_key_report`. Raw files are opened read-only; nothing is
moved, renamed or "repaired".

### Discovery

`discover_sources` accepts only `rtt_YYYY_MM.csv` (anchored, case-sensitive,
month 01–12). RTT-*like* names that break the contract (`rtt_2026_4.csv`,
`rtt_2026_13.csv`, `RTT_2026_06.CSV`, `…​.csv.bak`) are surfaced as
`malformed_candidates`; unrelated files go to `ignored`. Output order is
`sorted((reporting_month, filename))` — never filesystem order or mtime.

### Period policy

`^RTT-<MonthName>-<YYYY>$` (English month, case-insensitive) →
canonical `reporting_month` `"YYYY-MM"`. The raw `Period` column is never
overwritten. The canonical month must equal the filename month; more than one
distinct `Period` value in a file → rejected.

### Manifest / source registry

`data/raw/manifest.json` (tracked): one entry per byte-stream —
`{reporting_period, file, sha256, selected, revision_note, source_url}`.
`SourceRegistry.load` validates shape, filename↔period agreement, 64-hex
digests, `(period, sha256)` uniqueness, **≤ 1 `selected` per month**, and
**exactly one `selected`** whenever a month lists multiple distinct-hash
releases. Unknown provenance (URL, download time, publication date) is `null` —
**not fabricated**.

### Hashing

`sha256_file` streams the exact raw bytes. `count_data_rows` uses `csv.reader`
(CSV-aware record counting — **not** raw newline counting) as the independent
row-conservation cross-check against the loaded frame.

### Revision / re-release policy

`SourceRegistry.resolve_month`: same month + **same** SHA-256 → one artifact
(identical duplicates noted, not re-ingested); same month + **different**
SHA-256 → accepted only if exactly one observed digest is a `selected` registry
entry, otherwise `AmbiguousRevisionError` — **fail closed**. Never resolved by
file order, mtime, filename sort, size or discovery order. NHS revision metadata
is not invented.

### Candidate-key enforcement

Per file in `accept_month` (all five columns present; no missing **or
whitespace-only** key cell; unique). On the combined frame in `combine_months`,
asserted **both** directly (columns present, no missing cell,
`duplicated(subset=key) == 0`) **and** via `candidate_key_report(...).usable`
(`CombinedKeyError` otherwise).

### Monthly acceptance gate — `accept_month` (9 blocking conditions)

1. file missing / unreadable
2. filename not the exact production contract
3. provenance not establishable (SHA-256 not in the registry and no
   `expected_sha256`), or a supplied `expected_sha256` disagrees
4. `Period` absent / blank / unparseable / more than one distinct value /
   disagrees with the filename month
5. not the exact canonical 105-band schema (+ missing key/measure columns,
   duplicate headers) — `semantics.validate_extract`
6. fails to load — negative values, etc. — `semantics.load_rtt_csv`
7. loaded row count ≠ the independent CSV-aware streamed data-row count
8. candidate key: a column absent, a missing / whitespace-only key cell, or not
   unique
9. the registry lists more than one release for the month and this file's
   byte-stream is not the `selected` one

A rejected file is only **logically** rejected — left exactly where and as it
is.

### Cross-month diagnostics (warnings, never rejection)

`mapping_diagnostics` — code↔name changes, name↔code collisions
(`within_month` / `cross_month`), codes appearing / disappearing — for Provider,
Commissioner, Treatment Function, Provider Parent, Commissioner Parent, keeping
`<NA>` name groups. `coverage_diagnostics` — per-month row / part / TFC counts
and missingness prevalence. `part2a_subset_diagnostics` — the frozen
`part_2a_subset_conformance` per month. Any grouping over a nullable dimension
uses `dropna=False`.

### Provenance columns (the only additions)

`source_file`, `source_sha256`, `reporting_month` (`"YYYY-MM"`),
`source_row_index` = **0-based position of the row among its source file's
parsed CSV data records** (what `pandas.read_csv` yields) — *not* a physical
line number. The original `Period` column is retained unchanged. No wall-clock
timestamp enters row-level identity.

### Parquet publication

`write_combined_parquet` → `data/interim/rtt_combined.parquet` (pyarrow): wide
NHS structure, nullable `Int64` / `string` dtypes, `<NA>` missingness and
deterministic row order all preserved. Sidecar
`rtt_combined.ingest_manifest.json` = observed ingestion evidence, with a
`deterministic` block (reproducible) and a `run` block (timestamp, excluded from
determinism comparisons by `deterministic_manifest_view`). `roundtrip_check`
asserts **data-level** equality (shape, columns, values, per-column NA counts) —
not byte-for-byte file hashing.

### Rejection behaviour

A rejected month is absent from `payloads`; `run_phase3` refuses to produce the
combined dataset unless every discovered month was accepted (`ok = False` + an
explanatory note otherwise). A rejected file cannot partially contaminate
output.

---

## 3. Real-data findings (April, May, June 2026 — one shared ingestion path)

### Per month

| Month | File | SHA-256 (observed = expected) | Rows (loaded = streamed) | Internal `Period` → canonical | 105-band schema | Candidate key | Acceptance |
|---|---|---|---|---|---|---|---|
| 2026-04 | `rtt_2026_04.csv` | `0486aca5…a56e9` ✓ | 180,781 = 180,781 | `RTT-April-2026` → 2026-04 | OK | usable | **accepted** |
| 2026-05 | `rtt_2026_05.csv` | `fee364bc…a5707` ✓ | 178,171 = 178,171 | `RTT-May-2026` → 2026-05 | OK | usable | **accepted** |
| 2026-06 | `rtt_2026_06.csv` | `edc3927e…d67f02` ✓ | 182,411 = 182,411 | `RTT-June-2026` → 2026-06 | OK | usable | **accepted** |

No important warnings beyond the cross-month membership notes below.

### Combined dataset

| | |
|---|---|
| Included months | 2026-04, 2026-05, 2026-06 |
| Total rows | **541,363** = 180,781 + 178,171 + 182,411 |
| Row conservation | exact (asserted) |
| Columns | 125 (121 source + 4 provenance) |
| Candidate-key uniqueness | unique **and** `usable` on the combined frame |
| Provenance completeness | every row carries `source_file`, `source_sha256`, `reporting_month`, `source_row_index` |
| Parquet roundtrip | data-level equal (`{"ok": true, "problems": []}`) |
| Determinism | identical rows / order / values / provenance and identical `deterministic` manifest block across re-runs and payload-order shuffle |

### Cross-month findings

| Check | Result |
|---|---|
| Schema / header | **no drift** — identical 121-column header all three months; all pass `validate_extract` |
| `Period` format | `RTT-<MonthName>-<YYYY>`, one value per file, agrees with filename |
| Code ↔ name maps (all 5 dimensions) | **no drift** across the three months |
| RTT part structure | all five parts present each month |
| Treatment-function coverage | 24 codes each month, identical set |
| Provider / commissioner membership | minor churn (≈1 retired April→May, ≈9 new by June; commissioner `Y63` first appears in June) — **warning only** |
| Name ↔ code collision | only `DUCHY HOSPITAL` → `NT447` + `NVC04` (known, within-month) |
| Missingness prevalence | stable (`Total` ≈72 % blank, unknown-clock ≈81 %, `Total All` 0 %, all-bands-blank ≈20 %) |
| **`Part_2A > Part_2` (P2-U7)** | April **0** violations (5 groups with no matching `Part_2`); May **1** — new instance `NT230` / `05V` / `C_100` (`Part_2A = 2 > Part_2 = 1`); June **2** — `RTG` / `84H` / `C_502` and its `C_999`. Values preserved and flagged, **never capped**. |
| Contradiction to a frozen Phase 2 decision | **none** |

---

## 4. Tests

| Suite | Count | Result |
|---|---|---|
| `tests/test_profile.py` (Phase 1) | 47 | pass, unchanged |
| `tests/test_semantics.py` (Phase 2) | 51 | pass, unchanged |
| `tests/test_ingest.py` (Phase 3, new) | 55 | pass |
| `tests/test_crossmonth.py` (Phase 3, new) | 17 | pass |
| **Total** | **170** | **170 passed, 0 failed, 0 skipped** (`pytest -q`, ≈12 s) |

New tests cover every brief §14 item: discovery (valid / unrelated / malformed /
deterministic order); hash & provenance (stable, content-sensitive, completeness
required); Period (valid / missing / malformed / multiple / filename mismatch);
the frozen 105-band rejection set through `accept_month`
(drop-interior / duplicate / extra); candidate key (valid / missing /
whitespace / duplicate / combined uniqueness); revision handling (same-hash no
double-ingest / different-hash fail-closed / explicit selection order-
independent); missingness (blanks not zeroed, all-missing band distribution
still `<NA>` after combine + Parquet roundtrip, literal `NULL` preserved);
conservation (per-file, combined, rejected-file non-contamination); mapping-
diagnostic classification; and payload-shuffle determinism.

Relevant warnings: only benign Windows Jupyter/zmq notices during notebook
execution.

---

## 5. Notebook / artifacts

| Artifact | Status |
|---|---|
| `notebooks/03_multi_month_ingestion.ipynb` | **executes cleanly** (`nbconvert --to notebook --execute`), 0 error outputs, all 10 code cells run; thin layer — all logic in `src/` |
| `notebooks/01_data_discovery.ipynb`, `notebooks/02_semantics_grain_validation.ipynb` | **not re-executed** — unchanged and independent of the new modules; their 98 tests pass |
| `data/interim/rtt_combined.parquet` (~19 MB) | generated, git-ignored, reproducible |
| `data/interim/rtt_combined.ingest_manifest.json` | generated, git-ignored (observed evidence, separate from the intended-source registry) |

---

## 6. Outstanding issues

| Item | Classification | Note |
|---|---|---|
| **P2-U7** — `Part_2A > Part_2` source exceptions (Apr 0 / May 1 `NT230`-`05V`-`C_100` / Jun 2 `RTG`-`84H`) | **FROZEN PHASE 2 ISSUE REQUIRING USER REVIEW** | Carried per D-022; preserved and flagged; no cap, no source edit. Surfaced here as required; no remediation taken. |
| **P2-U3** — cross-month stability / revised-release handling | NON-BLOCKING | **Addressed** by this ingestion path (per-file + combined schema/key checks; drift diagnostics; fail-closed revision policy). No drift observed Apr–Jun. |
| **P2-U5** — `Period` parsing / file-revision selection | NON-BLOCKING | **Addressed for ingestion** (canonical month, filename agreement, revision resolution). |
| `Period` → calendar month-end date; flow/stock temporal model in analysis | DEFERRED TO PHASE 4+ | Documented direction only. |
| Band long-reshape · analytical dataset · cleaning/imputation · dimensional model · DuckDB/SQL · KPIs · provider-type enrichment · trends/stats · Power BI · ML · Spark | DEFERRED TO PHASE 4+ | Deliberately not implemented. |
| P2-U1, P2-U2, P2-U4, P2-U6 | NON-BLOCKING | Untouched — out of Phase 3 scope. |

No `BLOCKING` items.

---

## 7. Final self-assessment

**READY FOR INDEPENDENT PHASE 3 AUDIT.**

All Phase 1/2 regression tests plus 72 new Phase 3 tests pass; April, May and
June use one reusable ingestion path; the frozen 105-band schema and
candidate-key contracts are enforced per file and on the combined frame;
SHA-256 provenance and revised-release selection are explicit and fail closed;
row conservation and missingness preservation are proven end to end including
the Parquet roundtrip; every combined row carries sufficient provenance; the
combined Parquet is deterministic at the data level; no Phase 4 transformation
has leaked into this phase; P2-U3 and P2-U5 are addressed and P2-U7 is preserved
and diagnosed; documentation matches the implementation; repository hygiene is
intact.

Claude does **not** declare a Phase 3 PASS and has **not** created a Phase 3 Git
milestone — that requires the project owner's approval and independent Codex
review. Nothing has been committed, tagged or pushed.

Project sequencing preserved: **Meaning → ingestion → transformation → model →
analysis → KPIs → presentation.** Phase 3 is ingestion and provenance only.
