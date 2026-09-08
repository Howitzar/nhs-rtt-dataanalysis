> **⚠️ SUPERSEDED IN PART (2026-09-07).** This is the *original* Phase 2
> completion report. It was independently audited
> (`docs/phase2_independent_audit.md`, PASS WITH CHANGES) and remediated.
> Statements here about (a) unknown-clock "never blank for 1A/1B",
> (b) blank ≡ 0 as a semantic conclusion, (c) NONC "102,482 pathways" and the
> per-part NONC counts, (d) the May-2026 benchmark, and (e) "108 columns exact
> matches / 23 detail rows per group" are **corrected** in
> `docs/phase2_remediation_report.md` and the updated `docs/rtt_semantics.md` /
> `docs/rtt_grain_and_aggregation.md`. Read those for the current state.

# Phase 2 Completion Report — Dataset Semantics, Grain & Arithmetic Validation

**Project:** NHS RTT Waiting Times Analytics
**Phase:** 2 — Dataset Semantics, Grain & Arithmetic Validation
**Development dataset:** `data/raw/rtt_2026_06.csv` (NHS England RTT provider extract, period `RTT-June-2026`; SHA-256 `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`)
**Date:** 2026-09-07
**Status:** implemented; Claude's recommended verdict **PASS**. Not accepted until independently reviewed.
**Companion docs:** `docs/rtt_semantics.md`, `docs/rtt_grain_and_aggregation.md`, `docs/assumptions.md`, `docs/decisions.md` (D-015…D-021).

Guard-rails honoured: raw files immutable (SHA-256 verified before/after every run); 105 week-band columns **not** reshaped; blanks **not** globally filled; **no** cleaned dataset / Parquet / DuckDB / star schema / KPIs / Power BI / multi-month ingestion; no new dependencies.

---

## A. Files created / changed

| File | Status | Purpose |
|---|---|---|
| `src/nhs_rtt/semantics.py` | **new** | Reusable Phase 2 logic: programmatic week-band identification (reuses `nhs_rtt.profile.classify_columns` / `check_week_bucket_sequence`); `load_rtt_csv` (nullable `Int64` numerics so blank `<NA>` ≠ explicit `0`; rejects negatives per NHS Annex B); `reconciliation_summary` / `reconciliation_mismatch_examples`; `blank_zero_summary`; `candidate_key_report`; `aggregate_vs_detail`; `treatment_function_rows`; `nonc_summary`; `incomplete_within_18wk`; `controlled_examples`; `run_phase2_analysis` orchestrator; `assert_raw_unchanged`. |
| `notebooks/02_semantics_grain_validation.ipynb` | **new** | Orchestrates and narrates the layered investigation (controlled examples → identities → blank/zero → grain/key → C_999 → NONC → 18-week reproduction), writes `outputs/phase2/`, re-verifies raw SHA-256. Executes end-to-end with 0 errors. |
| `tests/test_semantics.py` | **new** | 24 tests in three labelled groups (see §B). |
| `docs/rtt_semantics.md` | **new** | Field meanings, arithmetic model, C_999, NONC, blank-vs-zero, 18-week methodology — each with an evidence class and an NHS England citation table. |
| `docs/rtt_grain_and_aggregation.md` | **new** | Row grain, candidate composite key + uniqueness-evidence table, aggregation-safety matrix, ranked double-counting risks, recommended safe default query. |
| `docs/assumptions.md` | edited | New "Phase 2 resolutions" section mapping Phase 1 items A-01…A-17 → outcome + evidence class; "Carried forward" list P2-U1…P2-U6; "next validation step" updated. Original Phase 1 table preserved. |
| `docs/data_dictionary.md` | edited | `Total` / unknown-clock / `Total All` / week-band / `C_999` / RTT-part rows now point to the resolved semantics; "Not defined here (deferred)" → "Resolved in Phase 2". |
| `docs/decisions.md` | edited | D-015 (approach), D-016 (blank≡0 conditional), D-017 (arithmetic model), D-018 (natural key, no surrogate), D-019 (C_999 rule), D-020 (NONC handling), D-021 (outputs gitignored). |
| `.gitignore` | edited | `outputs/phase2/*` added (regenerable; durable record is in `docs/`). |
| `outputs/phase2/` | generated (gitignored) | `reconciliation_by_part.csv`, `blank_zero_by_part.csv`, `treatment_function_rows.csv`, `nonc_by_part.csv`, `controlled_examples.csv`, `mismatch_bandsum_eq_totalall.csv`, `facts.json`. |
| memory `phase2-status.md`, `MEMORY.md` | new / edited | Session-persistent summary of settled vs open questions. |

Phase 1 source (`src/nhs_rtt/profile.py`), Phase 1 tests, and the Phase 1 profile outputs were **not** modified.

---

## B. Test results

Command:

```bash
"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pytest -q
```

**71 passed** (~9 s) = 47 Phase 1 (`tests/test_profile.py`) + 24 Phase 2 (`tests/test_semantics.py`). 0 failed, 0 skipped (June file present).

Phase 2 test groups (kept explicitly separate per brief §7):

| Group | Count | What it locks |
|---|---|---|
| `TestCodeCorrectness` | 15 | Pure logic on tiny synthetic frames: `parse_week_band`, band-column ordering + broken-sequence rejection, `bands_up_to_weeks`, blank-vs-zero preserved on load, negative-value rejection, `band_sum` skip-NA vs fill-0, reconciliation verdict logic (HOLDS/FAILS/n/a + diff stats), candidate-key duplicate detection, `aggregate_vs_detail` reconcile + break, `blank_zero_summary` counts, `nonc_summary`, `incomplete_within_18wk`, `treatment_function_rows`. |
| `TestRawImmutability` | 2 | `assert_raw_unchanged` round-trips and detects a changed hash; `load_rtt_csv` does not write the file. |
| `TestJune2026DatasetInvariants` | 7 | Regression locks for **this file only** (explicitly labelled as observed, not domain truths; `skipif` file absent): shape 182,411×121 / 105 bands; every expected arithmetic identity HOLDS; candidate key unique (with and without `Period`) and breaks when Treatment Function Code is dropped; `C_999` reconciles on all 108 columns across 40,636 groups; Part_3 is count-only; `Total`/unknown collected for 1A/1B only; NONC prevalence (2,993 rows / 119 providers / 102,482 pathways); 18-week reproduction in the 60–70% band; raw SHA-256 == known value. |

Both notebooks re-executed via `jupyter nbconvert --to notebook --execute` — clean. Raw SHA-256 of all three `data/raw/*.csv` unchanged after the full run (June = `edc3927e…f02`).

---

## C. Key semantic findings

Evidence classes: **DOCS+DATA** = explicit NHS definition **and** shown in the June CSV; **DATA** = shown in June, not found verbatim in guidance; **DOCUMENTED** = NHS definition, not row-testable from this aggregate file; **INFERRED**; **UNRESOLVED**.

| # | Conclusion | Class | Quantitative evidence | NHS source |
|---|---|---|---|---|
| 1 | **Row grain** = Provider × Commissioner × Treatment Function × RTT Part (× Period). | CONFIRMED — DOCS+DATA | candidate key unique for 182,411 / 182,411 rows | S1 §10.1.1.2, §10.1.4 |
| 2 | **RTT Part Types:** `Part_1A` completed-admitted, `Part_1B` completed-non-admitted, `Part_2` incomplete (month-end snapshot), `Part_2A` incomplete with decision-to-admit, `Part_3` count of new RTT periods (clock starts). "DTA" = decision to admit. | CONFIRMED — DOCS+DATA | rows 18,803 / 32,351 / 63,355 / 30,548 / 37,354 | S1 §10.1.1.2, terminology |
| 3 | **105 week-band columns** are mutually-exclusive weekly wait bands, allocated by days waited (0-1 wk = 0–7 days; a 126-day / 18-week wait sits in the 17-18 band; `Gt 104` = ≥729 days). Populated for Parts 1A/1B/2/2A only. | CONFIRMED — DOCS+DATA | Part_3: 37,354 / 37,354 rows all-band-blank; exact reconciliation is only possible if the bands partition the population | S1 §10.1.1.3, §10.1.7 |
| 4 | **`Patients with unknown clock start date`** = patients whose RTT clock-start date could not be identified, so cannot be band-placed; an **additive** term to `Total All`; collected for Parts 1A/1B only. | CONFIRMED — DOCS+DATA | on the 71 (1A) / 235 (1B) rows with unknown > 0, `Total All − Σbands = unknown` exactly | S1 §10.1.5, Annex B |
| 5 | **`C_999` / "Total"** treatment function is a pre-computed aggregate = exact sum of the 23 detail treatment functions on **every** numeric column. | CONFIRMED — DOCS+DATA | 40,636 / 40,636 `(provider, commissioner, part)` groups reconcile; 0 of 108 columns mismatch | S1 Annex B ("Incorrect totals – where the total is a sum over all treatment functions") |
| 6 | **`Part_2A` ⊆ `Part_2`** (DTA pathways are a subset of incomplete pathways); parts are otherwise distinct populations measured on distinct event bases. | DOCUMENTED — not row-testable here | — | S1 Annex B ("Part 2A … should be less than or equal to Part 2") |
| 7 | **`Commissioner Org Code = NONC`** = non-English (e.g. Welsh/Scottish) commissioner; present in the raw return; excluded from England published performance. | CONFIRMED — DOCS+DATA | 2,993 rows / 119 providers / all 24 TFCs / all 5 parts / 102,482 pathways | S1 §10.1.8, §10.1.9.2, Annex B |
| 8 | **Independent-sector providers are in scope** — not every `Provider Org Code` is an NHS trust. | CONFIRMED — DOCS+DATA | SpaMedica, Optegra, Practice Plus, etc. among the 537 provider codes | S1 §10.1.1.1 |
| 9 | **Blank ≡ explicit 0** within a populated weekly distribution (Parts 1A/1B/2/2A). Blank `Total`/unknown for Parts 2/2A/3, and every Part_3 band, = structural non-applicability. | CONFIRMED — DATA | band sum reconciles to `Total` with and without filling blanks (100%); ~3,431 rows mix `0` and blank band cells; `Total`/unknown 100% blank for 2/2A/3 vs 0% for 1A/1B | S1 Annex B (internal-total validation) |

**NHS sources**

| # | Title | Version / date | URL | Accessed |
|---|---|---|---|---|
| S1 | Recording and reporting referral to treatment (RTT) waiting times for consultant-led elective care (NHS England, PRN01045) | v5.0, 11 Feb 2025 | https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2025/02/Recording-and-reporting-RTT-waiting-times-guidance-v5.0-Feb25.pdf | 2026-09-07 |
| S2 | Statistical Press Notice — NHS RTT waiting times data, May 2026 | published 9 Jul 2026 | https://www.england.nhs.uk/statistics/wp-content/uploads/sites/2/2026/07/May26-RTT-statistical-press-notice-PDF-574K-3jBgba.pdf | 2026-09-07 |
| S3 | Consultant-led Referral to Treatment Waiting Times Rules and Guidance | ongoing | https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-guidance/ | 2026-09-07 |
| S4 | RTT Waiting Times — Consultant-led RTT Data 2026-27 | 2026-27 | https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/rtt-data-2026-27/ | 2026-09-07 |

---

## D. Arithmetic reconciliation — exact for 100% of applicable June rows

Source: `outputs/phase2/reconciliation_by_part.csv` (every `expected_identity` row has `verdict = HOLDS`, `n_mismatch = 0`).

| RTT Part Type | Relationship that HOLDS exactly | n rows | Notes |
|---|---|---|---|
| `Part_1A` | `Total = Σ(105 bands)` **and** `Total All = Total + unknown-clock` | 18,803 | `Σbands == Total All` "fails" on exactly 71 rows (unknown > 0), diff = −unknown |
| `Part_1B` | `Total = Σ(105 bands)` **and** `Total All = Total + unknown-clock` | 32,351 | same, 235 rows |
| `Part_2` | `Total All = Σ(105 bands)` | 63,355 | `Total` and unknown-clock not collected → blank on every row |
| `Part_2A` | `Total All = Σ(105 bands)` | 30,548 | `Total` and unknown-clock not collected → blank on every row |
| `Part_3` | none | 37,354 | 105 bands + `Total` + unknown all blank; `Total All` is a standalone count of new clock starts |

Consolidated model:

* **Completed pathways (1A, 1B):** `Total All = Σ(105 bands) + unknown-clock`, and `Total = Σ(105 bands)`.
* **Incomplete pathways (2, 2A):** `Total All = Σ(105 bands)`.
* **New RTT periods (3):** `Total All` only — a count, no distribution.

No blanks were treated as 0 to obtain these identities (they were derived with blanks kept as `<NA>`; the blank≡0 equivalence within a band is a separate result — §G).

---

## E. Grain / candidate-key result

**Best-supported key:**

```
Period · Provider Org Code · Commissioner Org Code · RTT Part Type · Treatment Function Code
```

Uniqueness evidence (`outputs/phase2/facts.json`, `nhs_rtt.semantics.candidate_key_report`):

| Key | Unique? | Duplicate groups | Excess rows |
|---|---|---|---|
| the 5-column key above | **yes** | 0 | 0 |
| 4-column (drop constant `Period`) | **yes** | 0 | 0 |
| drop `Commissioner Org Code` | no | 16,377 | 163,659 |
| drop `Treatment Function Code` | no | 40,636 | 141,775 |
| add parent codes | yes | 0 | 0 (parents redundant) |

**Caveats:** the key is empirically unique for June 2026 and matches the documented collection grain (S1 §10.1.1.2), but NHS England publishes no primary-key statement for this extract; cross-month stability is untested (P2-U3). **No surrogate/hash key was introduced** — a later phase should assert this natural key's uniqueness per file so a future collision fails loudly.

---

## F. Aggregation-safety rules & double-counting warnings

Full matrix: `docs/rtt_grain_and_aggregation.md` §4.

**Safe to filter / group / sum across:** `Provider Org Code`; `Commissioner Org Code` (exclude `NONC` for England performance); `Provider Parent` / `Commissioner Parent` (labels on detail rows — grouping by them aggregates the underlying provider rows; no parent-level aggregate rows exist).

**Never sum across:**

1. **`Treatment Function Code` without first excluding `C_999`.** The 23 detail codes sum exactly to the `C_999` row on every column. Including both doubles every pathway. → for specialty analysis filter `Treatment Function Code != "C_999"`; for a cross-specialty total use the `C_999` row directly.
2. **`RTT Part Type`.** 1A/1B/2/2A/3 are different populations on different event bases, and **`Part_2A` ⊆ `Part_2`** (S1 Annex B). Summing parts (or `Part_2 + Part_2A`) double-counts. Pick one part per analysis.
3. **Snapshot parts (`Part_2`, `Part_2A`) across `Period`.** An open pathway recurs in every monthly snapshot. Cross-month sums are valid only for flow parts 1A/1B/3. (Carried forward — not testable in this single-month file.)

**Join/group on codes, not names:** `DUCHY HOSPITAL` → provider codes `NT447` + `NVC04`; 8 commissioner codes (`NONC`, `Y56`, `Y58`–`Y63`) share a blank name.

**Recommended safe default (specialty-level):**

```python
df[
    (df["Treatment Function Code"] != "C_999")   # detail only
    & (df["RTT Part Type"] == "<one part>")       # never mix parts
    & (df["Commissioner Org Code"] != "NONC")     # for England performance
].groupby(["Provider Org Code", "Treatment Function Code"])[<band range or Total All>].sum()
```

---

## G. Missingness result

**Established (CONFIRMED — DATA):**

* Blank and explicit `0` in a week band are **arithmetically identical** ("no patients in that band") for the banded parts 1A/1B/2/2A — band sums reconcile to `Total` with *and* without filling blanks (100%), and ~3,431 rows freely mix `0` and blank band cells.
* Blank `Total` / unknown-clock on **all** Part_2/2A/3 rows (0% on 1A/1B), and **all 105 bands** on every Part_3 row, is **structural non-applicability** — those columns are not part of those parts' collection.
* → Phase 1 assumption A-01 resolved **conditionally** (D-016): a blank→0 rule is adopted only for the banded distributions of Parts 1A/1B/2/2A; blanks elsewhere stay blank; the raw file is unmodified and `load_rtt_csv` keeps blank as `<NA>`.

**Not established (carried forward):**

* Whether a *whole* part returning blank/zero for a provider is non-reporting vs a genuine zero — needs cross-month data (S1 Annex B "Missing data").
* Whether incomplete pathways (2/2A) with an unknown clock start exist and are folded into a band — `Total All = Σbands` exactly for 2/2A leaves no residual to locate them (P2-U2; INFERRED negligible / not separately collected).

---

## H. `C_999` result

`C_999` (`Treatment Function Name = "Total"`) is the **exact** sum of the 23 detail treatment functions (`C_100`…`C_502` plus the `X02`–`X06` "Other …" groupers), verified column-by-column across all 105 bands + `Total` + unknown-clock + `Total All` (108 columns), for **every** one of the **40,636** `(Provider Org Code, Commissioner Org Code, RTT Part Type)` groups, with **zero** mismatching columns (`nhs_rtt.semantics.aggregate_vs_detail`). This matches NHS validation (S1 Annex B).

Consequence: `C_999` is an already-aggregated total, not a specialty. **Aggregating `C_999` together with any specialty row double-counts every pathway.** Adopted rule (D-019): exclude `C_999` for specialty analysis; use it directly for a cross-specialty total; never both. `X02`–`X06` are documented leaf groupers within the 23 detail set (S1 §10.1.4), not further decomposed and not overlapping the named codes (the exact 23-code reconciliation to `C_999` rules out overlap among them).

---

## I. `NONC` result

`Commissioner Org Code = NONC` denotes pathways commissioned by **non-English commissioners** (patients treated in England whose commissioner sits in Wales/Scotland), reported under `NONC` in the aggregate monthly return only (S1 §10.1.8, §10.1.9.2; the record-level WLMDS uses the specific code). It is listed as a valid aggregate-return commissioner code in S1 Annex B.

June prevalence (`outputs/phase2/nonc_by_part.csv`): **2,993 rows** (1.6% of rows), **119 providers**, all 24 treatment functions, all 5 RTT parts, **102,482 pathways** (`Total All`) — concentrated in `Part_2` (1,022 rows / 62,312 pathways).

**Recommended analytical treatment:** retain `NONC` rows in the analytical dataset (valid activity), but **exclude them when reproducing NHS England published performance** (the NHS Constitution 18-week standard concerns English commissioners' patients). Impact is small: excluding `NONC` moves the June "% incomplete ≤ 18 weeks (Part_2 / Treatment Function Name = Total)" from 65.77% to 65.83%. `NONC` rows were **not** deleted from anything in Phase 2 (D-020).

---

## J. Unresolved questions (deliberately not forced)

| ID | Question | Why unresolved |
|---|---|---|
| P2-U1 | Reproduce the **exact** NHS England published headline "% incomplete within 18 weeks". | Requires the non-submitting-trust estimation method (S2 "figures include estimates for missing acute trusts"). The June Statistical Press Notice / RTT Overview Timeseries were not available at Phase 2 time. Current reproduction is *shape only*: **65.83%** (June raw, exclude NONC) vs published **65.6%** (May 2026, incl. estimates); >52-week incomplete ≈ 103,318 vs 104,734 published. |
| P2-U2 | Do incomplete pathways (2/2A) with an unknown clock start exist and get folded into a band, or are they simply out of scope for those parts' columns? | `Total All = Σbands` exactly for 2/2A → no residual to locate them. INFERRED negligible / not separately collected. |
| P2-U3 | Cross-month stability of the candidate key and of provider/commissioner code ↔ name. | Needs multi-month data (out of scope for Phase 2). |
| P2-U4 | Provider organisational-type classification (NHS trust vs independent sector vs interface). | Needs the ODS `etr` / `ephp` / `ephpsite` / `ect` reference files (S1 §10.1.1.1 fn.19); not yet ingested. |
| P2-U5 | `Period` → calendar month-end mapping; cross-file key semantics. | Single `Period` value in this file. |
| P2-U6 | Full per-band day ranges. | S1 §10.1.7 enumerates only the 0-1, 17-18 and 104+ bands; the rest are inferred from the stated pattern. |

---

## K. Decisions requiring the analyst's sign-off (brief §12)

1. **Adopt blank ≡ 0 inside banded distributions (D-016).** Evidence: exact two-way reconciliation + NHS internal-total validation (S1 Annex B); it changes **no computed value**. Alternative: treat every blank as strictly unknown — safe but forces skip-NA everywhere and forfeits the "exact vs `Total`" claim. **Recommendation: adopt as scoped** (banded parts only; raw file untouched; blanks elsewhere preserved).
2. **Rely on the natural candidate key now (D-018), asserting uniqueness per file**, vs waiting for ≥2 months of data. Alternative consequence: dimensional modelling in Phase 3 is blocked until multi-month scope is authorised. **Recommendation: proceed**, with a hard per-file uniqueness assertion.

---

## L. Definition-of-done checklist (brief §13)

| # | Question | Answer | Where |
|---|---|---|---|
| 1 | What does a row represent? | Provider × Commissioner × Treatment Function × RTT Part (× Period) waiting-time distribution/count. | rtt_semantics §2; grain doc §1 |
| 2 | What do the waiting-time bands represent? | 105 mutually-exclusive weekly wait bands (by days waited), for Parts 1A/1B/2/2A only. | rtt_semantics §3 |
| 3 | How do the bands relate to `Total`? | 1A/1B: `Total = Σbands`. 2/2A: `Total` not collected. | rtt_semantics §4.2; recon table |
| 4 | What does unknown-clock represent? | Patients with no identifiable clock-start date; not band-able; additive to `Total All`; 1A/1B only. | rtt_semantics §4.1 |
| 5 | How does it relate to total fields? | 1A/1B: `Total All = Total + unknown`. Not present for 2/2A/3. | rtt_semantics §4.2 |
| 6 | Why are many week / `Total` fields blank — resolved? | Yes: structural non-applicability (2/2A/3 don't collect `Total`/unknown; Part_3 has no bands) + blank≡0 within a banded distribution. | rtt_semantics §5 |
| 7 | Are blank and zero semantically distinguishable? | Inside a banded distribution: no (both = "no patients"). Across parts/columns: yes (blank = not-applicable). | rtt_semantics §5 |
| 8 | What does `C_999` aggregate? | Exact sum of the 23 detail treatment functions on every numeric column. | rtt_semantics §6 |
| 9 | Which rows are detail vs aggregate? | Detail: 23 TFCs (141,775 rows). Aggregate: `C_999` (40,636 rows). No other aggregate row type. | grain doc §3 |
| 10 | Best-supported candidate composite key? | `Period · Provider Org Code · Commissioner Org Code · RTT Part Type · Treatment Function Code`. | grain doc §2 |
| 11 | Which dimensions may be safely aggregated? | See aggregation-safety matrix. | grain doc §4 |
| 12 | Exclusions/filters to reproduce common NHS measures? | Part_2 + `Treatment Function Name = Total` + exclude `NONC`; numerator = bands ≤ 18 weeks; denominator `Total All`. Reproduces the shape (~65.8%); exact headline needs non-submitter estimate. | rtt_semantics §9 |
| 13 | What remains unresolved? | P2-U1…P2-U6 (§J). | assumptions.md "Carried forward" |

All existing + new tests pass; the Phase 2 notebook executes cleanly end-to-end; raw-file immutability verified; documentation separates DOCS+DATA / DATA / DOCUMENTED / INFERRED / UNRESOLVED.

---

## M. Recommended Phase 2 verdict

**PASS.** Every definition-of-done question is answered with evidence and an explicit class; the arithmetic model is exact for 100% of applicable June rows; grain and a unique candidate key are established (natural, not surrogate); C_999, NONC, and blank-vs-zero are resolved; six items are deliberately left UNRESOLVED rather than forced. Two scoped decisions (K-1, K-2) are put to the analyst.

This is Claude's recommendation only. Phase 2 is not accepted until independently reviewed. Phase 3 has not begun.
