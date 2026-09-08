> **Follow-up (2026-09-07).** This first remediation was re-audited
> (`docs/phase2_closure_audit.md`): **P2-A02/A03/A05/A07/A10 CLOSED**;
> **P2-A01/A04/A06/A08/A09 PARTIALLY CLOSED** plus a new HIGH **P2-R01**
> (missing-as-zero path could certify an undefined comparison). Those residuals
> were fixed in a narrow closure patch — see
> `docs/phase2_closure_remediation_report.md` and decisions **D-028 / D-029 /
> D-030**. The resolution labels in §C below are this report's *claims*; the
> closure audit's table is the current authority.

# Phase 2 Remediation Report

**In response to:** `docs/phase2_independent_audit.md` (Codex, PASS WITH CHANGES,
findings **P2-A01 … P2-A10**).
**Date:** 2026-09-07. **Dataset:** `data/raw/rtt_2026_06.csv` (June 2026, SHA-256
`edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`).
**Not** a Phase 2 restart; **not** Phase 3. No new technologies; no reshaping;
no imputation of the loaded data; raw files unchanged.

---

## A. Files changed

| File | Change |
|---|---|
| `src/nhs_rtt/semantics.py` | Rewritten. `observed_band_sum` (skip-missing, `<NA>` iff all bands blank; replaces the misleading `band_sum(treat_blank_as_zero=)`). `reconciliation_summary` now reports per check: `policy` (strict / missing-as-zero), `n_in_subset`, `n_evaluated`, `n_missing_operand`, `n_excluded_missing`, `n_mismatch`, `verdict` (unqualified `HOLDS` only with full subset coverage; else `PARTIAL`/`FAILS`/`n/a`) — completed parts now test `Total + unknown == Total All` (strict, unknown-populated subset) **and** `Total == Total All` (strict, unknown-blank subset) **and** `Total + unknown(→0) == Total All` (explicit convention). New `reconciliation_coverage_by_part`. `aggregate_vs_detail` rewritten: union of groups, orphan counts (`n_agg_only_groups`, `n_detail_only_groups`), `n_groups_multiple_agg_rows`, detail-rows-per-group spread, and comparison-state classification (`cmp_numeric_both`/`cmp_numeric_mismatch`/`cmp_both_missing`/`cmp_agg_zero_vs_all_missing_detail`/`cmp_other_missing`); `reconciles_numeric` requires no orphans/dupes and zero numeric mismatch. `nonc_summary` split into `nonc_prevalence` (no pathway total), `nonc_pathways_by_part(representation=)` (per-part, one TFC representation), `nonc_raw_cell_checksum` (labelled uninterpreted). New `part_2a_subset_conformance`. New `validate_extract` (pre-pandas header/duplicate/key/measure/band-schema checks); `load_rtt_csv(validate=True)` now also `keep_default_na=False, na_values=[""]`. `candidate_key_report` → `is_unique=None` (never silent `True`) on a missing column, `usable` requires all cols present + no missing key cell + uniqueness. New `same_month_totals_check` + `JUNE_2026_SPN_UNESTIMATED`; `incomplete_within_18wk` gains `benchmark_june_2026_spn_unestimated`. `controlled_examples` rewritten as a curated real-row table (positive/blank unknown, Part_2/2A, RTG/84H exception, Part_3 with `<NA>` band sum). `run_phase2_analysis(source_path=)` writes the new tables. |
| `tests/test_semantics.py` | Rewritten: 36 tests, docstring group counts corrected, wrong key-drop comment fixed. New regressions for P2-A01…A09 (see §B). |
| `notebooks/02_semantics_grain_validation.ipynb` | Re-narrated for the corrected model; new cells for coverage, Part_2A conformance, NONC split, same-month benchmark; executes clean end-to-end. |
| `docs/rtt_semantics.md` | §1 sources (add **S5** user guidance, **S6** June 2026 SPN; May SPN demoted); §2 Part_2A ⊆ Part_2 + RTG/84H exception; §3 band-2021 claim scoped, "mutually exclusive" softened; **§4 rewritten** (unknown-clock blank counts, per-subset strict identities, missing-as-zero policy); **§5 rewritten** ("arithmetic compatibility, not semantic equivalence"); §6 C_999 (missingness states, detail-rows-per-group 1–23, zero-contribution policy); §7 disjointness/roll-up claims narrowed; **§9 rewritten** (same-month June benchmark); §10 P2-U1/U2/U5/U6 updated, **P2-U7** added. |
| `docs/rtt_grain_and_aggregation.md` | §2 key acceptance contract (K-2); §3 "reported level vs roll-up marker" (narrowed); §4 aggregation matrix updated (`dropna=False`, join multiplicity) + new **§4a count-conservation check**; §5 risks re-ranked (adds NA-parent data loss, join multiplicity); new **§6 Part_2A ⊆ Part_2 + RTG/84H**; §7 safe-default query uses `dropna=False`. |
| `docs/assumptions.md` | Phase 2 resolutions table: A-01 **narrowed** to an arithmetic convention; A-02/A-03 corrected + coverage/policy; A-07 evidence scoped; A-17/P2-U6 narrowed; carried-forward list updated; **P2-U7** added. |
| `docs/decisions.md` | **D-016 narrowed** (scoped June convention; earlier "blank ≡ 0" / "quality trigger diagnoses non-reporting" removed); **D-017** revised (coverage/policy); **D-019/D-020** wording revised; new **D-022** (Part_2A preserve & flag), **D-023** (same-month benchmark), **D-024** (NONC split), **D-025** (loader/key acceptance gates), **D-026** (coverage reporting), **D-027** (remediation umbrella). |
| `docs/data_dictionary.md` | `Total` / unknown-clock / `Total All` rows corrected (unknown-clock blank counts; observed-band-sum wording). |
| `docs/phase2_completion_report.md` | "SUPERSEDED IN PART" banner pointing here. |
| `outputs/phase2/*` | Regenerated (gitignored). New: `reconciliation_coverage_by_part.csv`, `nonc_pathways_by_part_c999.csv`, `part2a_subset_violations.csv`, `same_month_totals_check.csv`, `mismatch_positive_unknown.csv`. Removed: `nonc_by_part.csv`, `mismatch_bandsum_eq_totalall.csv`. |

Phase 1 source (`src/nhs_rtt/profile.py`), Phase 1 tests, and Phase 1 outputs
were not modified. Phase 1 notebook re-executed unchanged.

## B. Tests run and exact results

```bash
"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pytest -q
```
→ **83 passed** in ~9–11 s. 0 failed, 0 skipped (June file present).
Split: `tests/test_profile.py` **47** (Phase 1, unchanged), `tests/test_semantics.py`
**36** = 24 `TestCodeCorrectness` + 2 `TestRawImmutability` + 10
`TestJune2026DatasetInvariants`.

Both notebooks re-executed with `jupyter nbconvert --to notebook --execute`
— **0 errors**. Raw SHA-256 of all three `data/raw/*.csv` unchanged after the
full run (June = `edc3927e…f02`).

New/changed regressions map to findings:

| Finding | New tests |
|---|---|
| P2-A01 | `test_observed_band_sum_semantics` (`<NA>` iff all bands blank, not 0); `test_reconciliation_partial_verdict_when_rows_excluded` |
| P2-A02 | `test_reconciliation_reports_coverage_and_missing_operand`; `test_reconciliation_coverage_by_part_partitions`; `test_completed_unknown_blank_counts` (June 6,032 / 11,005 and both-present 12,771 / 21,346) |
| P2-A03 | `test_nonc_prevalence_has_no_pathway_total`; `test_nonc_pathways_by_part_one_representation`; `test_nonc_raw_checksum_is_labelled_uninterpreted`; `test_nonc` (per-part 1,224/4,478/31,156/7,734/6,649) |
| P2-A04 | `test_reconciliation_fails_on_broken_row`; `test_aggregate_vs_detail_orphan_and_dup_and_zero_missing` (orphan/dup/agg-zero cases) |
| P2-A05 | `test_part2a_subset_conformance_flags_violation`; `test_part2a_subset_exception_RTG_84H` |
| P2-A06 | `test_incomplete_within_18wk_math` (+ benchmark key); `test_same_month_totals_match_june_spn` |
| P2-A08 | `test_c999_reconciliation_states` (40,636 groups; 928,416 both-missing; 588,157 agg-zero-vs-all-missing; detail 1–23; 20,518 with 1; 18 with 23) |
| P2-A09 | `test_load_keeps_literal_NA_tokens_as_strings`; `test_load_rejects_duplicate_headers`; `test_load_rejects_missing_key_column`; `test_candidate_key_missing_column_is_not_unique_true`; `test_candidate_key_usable_requires_nonmissing_key_cells` |
| P2-A10 | `test_controlled_examples_shape`; corrected comments / group counts throughout |

## C. Codex findings — status

| ID | Severity | Status | Notes |
|---|---|---|---|
| **P2-A01** arithmetic equivalence presented as semantic | HIGH | **RESOLVED** | D-016 narrowed to a scoped June *numerical convention*; `rtt_semantics.md` §5 rewritten; skip-NA-vs-fill-0 "independent proof" claim and "quality trigger diagnoses non-reporting" removed; raw missingness preserved; not extended to future files. |
| **P2-A02** completed-part unknown-clock blanks mis-described | HIGH | **RESOLVED** | "never blank for 1A/1B" corrected everywhere; blank counts 6,032 / 11,005 and both-present 12,771 / 21,346 documented and tested; A/B/C split (both-present strict; unknown-blank strict `Total == Total All`; missing-as-zero convention over all rows). |
| **P2-A03** NONC "pathways" double-counted / part-mixed | HIGH | **RESOLVED** | `nonc_prevalence` (no pathway total) vs `nonc_pathways_by_part` (per part, C_999 representation: 1,224/4,478/31,156/7,734/6,649, "do not sum"); 102,482 retained only as a labelled `nonc_raw_cell_checksum`. Tests updated. NONC rows retained. |
| **P2-A04** reconciliation passes after losing coverage / hiding defects | HIGH | **RESOLVED** | `reconciliation_summary` reports subset / evaluated / excluded / missing-operand and refuses an unqualified `HOLDS` with exclusions. `aggregate_vs_detail` uses the group union, reports orphans + duplicate aggregates + comparison states; `reconciles_numeric` blocked by any of them. Counterexample regressions added. |
| **P2-A05** Part_2A > Part_2 count exception not checked | HIGH | **RESOLVED** | `part_2a_subset_conformance` added; June's **two** exceptions (`RTG`/`84H`/`C_502` and `C_999`, 2 vs 1) independently reproduced, documented (rule vs June conformance), and given a disposition (D-022: preserve & flag, never cap). Carried as P2-U7. |
| **P2-A06** cross-month comparison can't explain residual | MED | **RESOLVED** | May comparison withdrawn. Same-month **June 2026 SPN Table 1 unestimated** benchmark: raw file reproduces 7,147,562 / 318,650 / 1,307,837 / 1,930,912 and 65.8% **exactly** (`same_month_totals_check`). S5 cited for the CSV filters. P2-U1 restated (publication available; estimate-inclusive uplift still not implemented). |
| **P2-A07** aggregation instructions lose rows / overstate disjointness | MED | **RESOLVED** | `dropna=False` shown with a count-conservation check (§4a); the 489-row / 131,509-pathway default-`groupby` loss documented; "no other aggregate row type / everything else disjoint detail" narrowed to "no additional roll-up marker **observed**"; join-multiplicity and stock-vs-flow wording added; "23 detail rows per group" corrected to a 1–23 range. |
| **P2-A08** C_999 wording suppresses missingness / coverage | MED | **RESOLVED** | `rtt_semantics.md` §6 states "sum of the **available** non-C_999 rows … with the stated zero-contribution policy"; reports 40,636 groups (1 agg, ≥1 detail), detail 1–23 (18 with all 23, 20,518 with 1), 2,872,115 numeric / 928,416 both-missing / 588,157 agg-zero-vs-all-missing. Exclusion rule retained. |
| **P2-A09** loader/key not sufficient acceptance checks | MED | **RESOLVED** (for the agreed extract format) | `validate_extract` (raw-header duplicate check pre-mangle, required key/measure columns, band-schema); `load_rtt_csv` `keep_default_na=False, na_values=[""]` (literal `NULL` kept); `candidate_key_report` → `is_unique=None` on a missing column, `usable` gate. Not generalised into a Phase 3 ingester. |
| **P2-A10** examples / test descriptions overstate | LOW | **RESOLVED** | Curated `controlled_examples` (blank + positive unknown, Part_2A>Part_2, Part_3 with `<NA>` band sum); wrong key-drop comment fixed; group counts corrected; substantive regressions added (not count-padding). |

**Not resolved / deliberately deferred:** exact **estimate-inclusive** England
headline (P2-U1 — the non-submitter uplift is not implemented; the June
publication is now cited and its *unestimated* totals reproduce exactly);
provider organisational-type reference data (P2-U4). Both are explicitly
out of scope for this remediation per the audit's §N.

## D. Updated missingness conclusion

**Arithmetic compatibility established; semantic equivalence not established.**
For the June 2026 banded parts, the sum of *observed* band cells reconciles to
the reported totals, and stays exact if missing band (and missing unknown-clock)
contributions are also treated as `0`. This is an explicit, **scoped, non-
destructive numerical convention** applied per calculation — it does **not**
establish why a publisher serialised a cell as blank, whether a blank could be
unknown/withheld, or that the convention transfers to another return. Blank
`Total` / unknown-clock on Parts 2/2A/3 and every Part_3 band = **not
collected** (structural). Missing provider/commissioner/specialty *rows* cannot
be diagnosed as non-reporting from absence. Raw missingness is preserved
(`load_rtt_csv` keeps `<NA>`). Phase 1 A-01 is **narrowed**, not resolved.

## E. Updated completed-path arithmetic model

Per row of a completed part (1A/1B), exactly one of two strict subsets applies:

| Subset | Size (1A / 1B) | Strict identity (0 mismatches, full coverage) |
|---|---|---|
| unknown-clock **populated** | 12,771 / 21,346 | `Total + unknown == Total All` |
| unknown-clock **blank** | 6,032 / 11,005 | `Total == Total All` |

Both subsets: `observed_bandsum == Total` (all 18,803 / 32,351 rows). The
subsets are disjoint and partition the part. `Total + unknown == Total All`
extends to **all** rows only under the stated `missing-as-zero` convention
(applied to the 6,032 / 11,005 blank-unknown rows). Strict
`observed_bandsum == Total All` therefore fails by exactly `−unknown` on the
71 / 235 rows with a positive unknown-clock count.

Incomplete parts (2/2A): `observed_bandsum == Total All` strict, all rows;
`Total`/unknown not collected. Part_3: `Total All` only (a count);
`observed_bandsum` is `<NA>`, and a strict band identity is reported
`PARTIAL (37,354 excluded)`, deliberately not "HOLDS".

## F. Corrected NONC results

**Structural prevalence:** 2,993 rows (1.6%), 119 providers, all 24 treatment
functions, all 5 parts. *No pathway total at this level.*

**Pathway counts per RTT part** (C_999 representation; **do not sum**):

| Part | pathways |
|---|---|
| Part_1A | 1,224 |
| Part_1B | 4,478 |
| Part_2 | 31,156 |
| Part_2A | 7,734 |
| Part_3 | 6,649 |

The earlier **102,482** is `nonc_raw_cell_checksum` — the raw `Total All` sum
over all NONC rows — explicitly labelled *not a pathway population* (it adds
C_999 to its constituents and mixes parts). Earlier "Part_2 62,312" was
`2 × 31,156`. **Analytical treatment:** retain NONC rows; exclude
`Commissioner Org Code = NONC` for England published performance (S5);
excluding it moves the June "% within 18 weeks (Part_2 / Total)" from
65.773% to 65.826% (NONC contributes 16,735 / 31,156). **Coverage caveat:**
NONC submission is not mandatory (S5) — NONC rows are **not exhaustive** of
non-English activity.

## G. Reconciliation coverage behaviour

`reconciliation_summary` now emits, per check: `policy`, `n_in_subset`,
`n_evaluated`, `n_missing_operand`, `n_excluded_missing`, `n_match`,
`n_mismatch`, `diff_min/max`, `verdict`. `verdict = "HOLDS"` **only** when the
subset was fully evaluated (strict: `n_excluded_missing == 0`) with zero
mismatches; otherwise `"HOLDS (missing-as-zero convention)"` (with
`n_missing_operand` shown), `"PARTIAL (N rows excluded: missing operand)"`,
`"FAILS"`, or `"n/a"`. `reconciliation_coverage_by_part` proves the strict
subsets partition each part.

`aggregate_vs_detail` compares the **union** of aggregate/detail groups and
reports: `n_agg_only_groups`, `n_detail_only_groups`,
`n_groups_multiple_agg_rows`, detail-rows-per-group min/max + `n at 1` +
`n at max`, and per-comparison `cmp_numeric_both` / `cmp_numeric_mismatch` /
`cmp_both_missing` / `cmp_agg_zero_vs_all_missing_detail` / `cmp_other_missing`.
`reconciles_numeric` is `True` only with no orphan groups, no duplicate
aggregate rows, and zero numeric mismatch. `reconciles_missing_as_zero` is
reported separately as the (stated-convention) view.

## H. Updated C_999 result

For each of the **40,636** `(Provider, Commissioner, RTT Part)` groups: exactly
one `C_999` row, at least one non-C_999 row, **0 orphan groups**, **0 duplicate
aggregate rows**. Detail rows per group range **1–23** (20,518 groups carry
one; only **18** carry all 23). Over 4,388,688 group×column comparisons:
**2,872,115** numeric-on-both-sides with **0 mismatches**; **928,416**
both-missing; **588,157** `C_999`-zero vs all-missing detail. Under the stated
zero-contribution convention for missing cells every group reconciles; under
strict nullable equality the 588,157 are not observed numeric equalities.
**Rule retained:** for one provider/commissioner/period/part use `C_999` alone
**or** the reported non-C_999 rows alone — never both.

## I. Part_2A subset-conformance result and decision

**Rule (DOCUMENTED, S1 Annex B):** `Part_2A` count ≤ `Part_2` count for
matching provider / commissioner / treatment function.
**June conformance:** 30,548 `Part_2A` groups, all with a matching `Part_2`
key; **30,546 conform, 2 violate** — `RTG` / `84H` / `C_502` and the
corresponding `C_999`, each `Part_2A = 2` vs `Part_2 = 1` (a detail row and
its total). Independently reproduced.
**Decision (D-022):** preserve source values; flag the violations
(`outputs/phase2/part2a_subset_violations.csv`); **do not** cap `Part_2A` or
alter `Part_2`. Any measure that assumes `Part_2A <= Part_2` (e.g.
`Part_2 − Part_2A`, DTA share) must validate the invariant per group before
calculating. Carried forward as P2-U7. Publisher correction is not a
prerequisite for honest acceptance.

## J. Updated grain / key contract

Grain (DOCUMENTED, S1 §10.1.1.2/§10.1.4): Provider × Commissioner × Treatment
Function × RTT Part (× Period). Candidate natural key
`[Period, Provider Org Code, Commissioner Org Code, RTT Part Type, Treatment
Function Code]` — for June, `is_unique=True` and `usable=True`. **Acceptance
contract (K-2, APPROVE WITH MODIFICATION):** all five columns present; **no
missing key cell**; uniqueness holds **for each incoming file**; a defined
policy for **revised releases** (`Period` does not distinguish a revision).
`candidate_key_report(...)["is_unique"]` alone is insufficient — it returns
`None` when a column is absent and `usable=False` until every precondition
passes. **Not** an NHS-guaranteed primary key; **not** a patient/pathway
identifier. No surrogate key introduced.

## K. Same-month June benchmark reproduction

From `rtt_2026_06.csv`, `Treatment Function Name = Total`, exclude `NONC`
(`same_month_totals_check`), vs **S6 (June 2026 SPN, Table 1, unestimated)**:

| Measure | raw file | S6 unestimated | match |
|---|---|---|---|
| Incomplete pathways | 7,147,562 | 7,147,562 | ✅ |
| % incomplete within 18 weeks | 65.826% → 65.8% | 65.8% | ✅ (1 dp) |
| Completed admitted | 318,650 | 318,650 | ✅ |
| Completed non-admitted | 1,307,837 | 1,307,837 | ✅ |
| New RTT periods | 1,930,912 | 1,930,912 | ✅ |

Filters cited from **S5** ("Reproducibility and derived measures"): Part_2,
`Treatment Function Name = Total`, bands 0-1 … 17-18, denominator `Total All`,
`Commissioner Org Code <> NONC`. The published **estimate-inclusive** headline
(S6 page 1) additionally uplifts for non-submitting trusts RHQ and RA9; that
uplift is **not** implemented (P2-U1). Matching rounding at 1 dp is not exact
estimate-inclusive reproduction.

## L. Documentation changes

`docs/rtt_semantics.md`, `docs/rtt_grain_and_aggregation.md`,
`docs/assumptions.md`, `docs/decisions.md`, `docs/data_dictionary.md` updated
as in §A; `docs/phase2_completion_report.md` carries a "SUPERSEDED IN PART"
banner. New source citations: **S5** RTT statistics user guidance, **S6**
June 2026 SPN. The May 2026 SPN is retained only as context (not June
evidence).

## M. Remaining unresolved questions

| ID | Question | Status |
|---|---|---|
| P2-U1 | Exact **estimate-inclusive** England headline (non-submitter uplift). | UNRESOLVED. June publication available; **unestimated** Table 1 reproduces exactly; the RHQ/RA9 uplift is not implemented. |
| P2-U2 | Do incomplete pathways with an unknown clock start exist / get folded into a band? | UNRESOLVED. The "negligible / folded" inference is **withdrawn**. |
| P2-U3 | Cross-month code↔name / key stability; revised-release handling. | UNRESOLVED; required for multi-month ingestion. |
| P2-U4 | Provider organisational-type classification. | UNRESOLVED until ODS `etr`/`ephp`/`ephpsite`/`ect` files are ingested. |
| P2-U5 | `Period` literal → calendar month-end; file revisions. | Part-specific temporal meaning (flow vs month-end stock) documented; parsing/revisions deferred. |
| P2-U6 | Full per-band day ranges. | **Narrowed:** 5 NHS worked examples + stated sequence; intermediate bounds derived and labelled derived. |
| P2-U7 | `RTG` / `84H` `Part_2A > Part_2` count exception. | Carried forward as a data-quality issue; raw preserved & flagged; subset-derived measures must validate the invariant first. |

## N. Recommendation

**READY FOR CODEX RE-REVIEW.**

All ten findings are addressed: the semantic/arithmetic wording is scoped to
what the evidence supports, coverage and missingness are reported explicitly,
the NONC and Part_2A corrections are implemented with tests, the same-month
June benchmark replaces the May comparison, and the loader/key helpers now gate
malformed input. The independently reproduced June numbers are unchanged.
Six items remain explicitly UNRESOLVED (P2-U1…U7 above) rather than forced.

Provisional analyst decisions **K-1** and **K-2** are recorded as
**APPROVE WITH MODIFICATION** (D-016 narrowed; D-018/D-025 key acceptance
contract). This is Claude's recommendation only — Phase 2 is not declared PASS
here, and Phase 3 is not begun.
