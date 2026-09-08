# Phase 2 Closure Remediation Report

**In response to:** `docs/phase2_closure_audit.md` (Codex closure review, PASS
WITH CHANGES — 5 CLOSED, 5 PARTIALLY CLOSED, 1 new HIGH **P2-R01**) and the
closure brief.
**Date:** 2026-09-07. **Dataset:** June 2026 only, SHA-256
`edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02`.
**Scope:** the residual blockers **P2-A01, P2-A04/P2-R01, P2-A06, P2-A08,
P2-A09** only. No Phase 3, no new technologies, raw NHS data unchanged, no
broadening. The 5 already-CLOSED findings and K-1/K-2 are untouched.

---

## A. Files changed

| File | Change |
|---|---|
| `src/nhs_rtt/semantics.py` | **P2-R01 / P2-A04:** `_reconcile` rewritten — a subset row is *evaluated* only when **both** operands are non-`<NA>` after applying **only** the explicitly-authorised zero-fill; any row still carrying a missing **required** operand (`Total All`, `Total`, an entirely unobserved band distribution) is excluded and counted for *both* policies (`n_missing_operand`, verdict `PARTIAL`, never a match); `n_match` derived from an explicit equality mask (not `n_evaluated − n_mismatch`); zero-evaluated / all-missing handled without a numeric-conversion error; new field `n_convention_rows`. `reconciliation_summary` callers: only `unknown-clock` blanks (and skip-missing bands) are zero-filled — **`Total` and `Total All` are never pre-filled**. **P2-A04 (aggregate):** `aggregate_vs_detail` gains `acceptable` — a policy-aware overall flag (no orphan groups, one aggregate row per group, zero numeric mismatch, `cmp_other_missing == 0`); `reconciles_numeric` retained but documented as a diagnostic; `cmp_other_missing` reported. **P2-A09:** new `expected_week_band_names()` (canonical 105) + `check_expected_band_schema()`; `validate_extract(require_full_band_schema=True)` and `load_rtt_csv(require_full_band_schema=True, default)` enforce the exact schema; `validate_extract` returns `expected_band_schema_ok`. `run_phase2_analysis` facts gain `c999_acceptable`. |
| `tests/test_semantics.py` | 51 Phase 2 tests (was 36). New: 8 band-schema regressions (`test_band_schema_accepts_exact_105` + parametrized `test_band_schema_rejects_malformed` × 7: drop-all / keep-one / drop-first / drop-open-end / drop-interior / duplicate / extra); 6 missing-as-zero regressions (missing `Total All` excluded; all-`Total All`-missing no TypeError; missing `Total` not zero-filled; authorised blank unknown still HOLDS; ordinary valid; broken-row FAILS with explicit match count); aggregate `test_aggregate_missing_vs_numeric_detail_not_acceptable`; `test_expected_week_band_names_is_canonical_105`. Synthetic non-schema tests load via a `_load()` helper (`require_full_band_schema=False`); `TestJune2026DatasetInvariants` uses the production gate. |
| `notebooks/02_semantics_grain_validation.ipynb` | Cell 1 prints the full `validate_extract` (incl. `expected_band_schema_ok`); re-executed, 0 errors. |
| `docs/data_dictionary.md` | **P2-A01:** the week-band row's "Within a banded row, blank ≡ 0" replaced with the scoped numerical zero-contribution convention wording (blank stays `<NA>`; arithmetic compatibility, not semantic equivalence; not transferable). **P2-A08:** the `C_999` bullet's "exact sum of the 23 detail rows on every numeric column, for all 40,636 groups" replaced with the 1–23 available-rows / 18-groups-carry-23 / missingness-states / "reconciliation under the convention ≠ observed equality" wording; analytical rule retained. |
| `docs/assumptions.md` | **P2-A06:** "Recommended next validation step" rewritten — the June 2026 publication **is** available; its unestimated Table 1 totals reproduce exactly (table); only the estimate-inclusive uplift (P2-U1) is unresolved; the May-65.6% cross-month comparison and "not available at Phase 2 time" statement are removed. |
| `docs/rtt_semantics.md` | §4.2 preamble rewritten for the corrected evaluation logic (both-operand requirement, `PARTIAL` for missing required operands, explicit-equality match count, `n_convention_rows`). §6 adds `cmp_other_missing == 0` and the `acceptable` flag. |
| `docs/rtt_grain_and_aggregation.md` | §2 "Status" adds the `validate_extract` gate; new "Extract-validation gate" subsection describing the exact 105-band contract. |
| `docs/decisions.md` | New **D-028** (missing-as-zero must not certify undefined comparisons), **D-029** (exact 105-band schema gate), **D-030** (closure remediation umbrella). |
| `docs/phase2_remediation_report.md` | Follow-up banner pointing to the closure audit + this report. |

Phase 1 source/tests/outputs untouched. Previously-CLOSED findings' code/wording untouched.

## B. Exact test results

```bash
"C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe" -m pytest -q
```
→ **98 passed** in ~10 s. 0 failed, 0 skipped. = `test_profile.py` **47**
(Phase 1, unchanged) + `test_semantics.py` **51** (39 `TestCodeCorrectness`
incl. 7 parametrized schema-reject cases + 2 `TestRawImmutability` + 10
`TestJune2026DatasetInvariants`).

Both notebooks re-executed with `jupyter nbconvert --execute` — **0 errors**.
Raw SHA-256 of all three `data/raw/*.csv` unchanged (June = `edc3927e…f02`).

## C. Residual finding status

| ID | Status | Basis |
|---|---|---|
| **P2-A01** | **RESOLVED** | The last active contradiction (`data_dictionary.md` "blank ≡ 0") is replaced with the scoped-convention wording matching D-016 / `rtt_semantics.md` §5. Doc-sync search (§G) finds no other active `blank ≡ 0` / "universal semantics" statement. Blank stays `<NA>` in the loaded data. |
| **P2-A04 / P2-R01** | **RESOLVED** | `_reconcile` now requires both operands numeric after only the authorised fill; missing `Total All` / `Total` / all-missing distributions are excluded (`PARTIAL`), never matched; `n_match` from an explicit equality mask; no numeric-conversion error on empty/all-missing. `aggregate_vs_detail` gains the policy-aware `acceptable` flag; `reconciles_numeric` labelled a diagnostic. Seven focused regressions (§E) plus the June invariant (`n_missing_operand == 0` on every expected check). |
| **P2-A06** | **RESOLVED** | `assumptions.md` next-step passage now states the same-month June benchmark (reproduces exactly) and confines the open item to the estimate-inclusive uplift (P2-U1). May-65.6% comparison and "June sources unavailable" removed from active docs; `decisions.md` D-023 retains them only as the *withdrawn* approach. No uplift implemented. |
| **P2-A08** | **RESOLVED** | `data_dictionary.md` C_999 bullet synchronised with the verified 1–23 available-rows description, the 18/20,518 group split, the both-missing and C_999-zero/all-missing-detail states, and "reconciliation under the convention ≠ observed equality". The use-C_999-OR-detail rule is retained. |
| **P2-A09** | **RESOLVED** | `validate_extract` / `load_rtt_csv` enforce the exact canonical 105-band schema by default (first `Gt 00 To 01`, ordered weekly sequence, open end `Gt 104 Weeks`, no missing interior/duplicate/extra). Zero bands, a single band, missing first, missing open-ended, missing interior, duplicate and extra are all rejected — 7 regressions + a positive 105-band test. Generic Phase 1 band discovery kept separate. Not a Phase 3 ingester. |

## D. Corrected missing-as-zero evaluation logic

For a check over `subset` with series `lhs`, `rhs` that already carry **only**
the authorised zero-fill:

1. `evalmask = subset & lhs.notna() & rhs.notna()` — a row is *evaluated* only
   when a genuine numeric comparison exists on both sides. This is the same for
   `strict` and `missing-as-zero`; the policies differ only in *which* inputs
   the caller was allowed to zero-fill first.
2. **Authorised fills only:** a blank `unknown-clock` contribution → 0 (D-016);
   band cells are skip-missing via `observed_band_sum` (`<NA>` iff *every* band
   is blank). **`Total` and `Total All` are never pre-filled.** So a row with a
   missing `Total All` (or missing `Total`, or an all-blank distribution) keeps
   an `<NA>` operand and is **excluded**.
3. `n_excluded = n_missing_operand = n_in_subset − n_evaluated`. `n_convention_rows`
   counts subset rows where an authorised fill was actually applied
   (informational).
4. Match counts from an explicit mask on the evaluated rows:
   `n_match = (lhs[evalmask] == rhs[evalmask]).sum()`,
   `n_mismatch = n_evaluated − n_match`. A missing comparison can never be
   credited as a match (there are none — evalmask excludes them).
5. `diff_min` / `diff_max` are `None` when `n_evaluated == 0` (no `float(<NA>)`).
6. Verdict: `n/a` (empty subset) → `FAILS` (any mismatch) →
   `PARTIAL (N rows excluded: required operand missing)` (any exclusion) →
   `HOLDS (missing-as-zero convention)` (authorised fill was used) → `HOLDS`.
   **An unqualified `HOLDS` is impossible while a required operand is missing.**

June: every `expected` check has `n_missing_operand = 0` and verdict `HOLDS` /
`HOLDS (missing-as-zero convention)`; the Part_3 diagnostic is
`PARTIAL (37,354 rows excluded: required operand missing)`.

## E. Synthetic counterexample results

| Fixture | Old (buggy) behaviour | New behaviour |
|---|---|---|
| **missing `Total All`** — 2 completed rows, one `Total All = 0`, one `Total All = <NA>` (`test_missing_as_zero_excludes_missing_total_all`) | `n_evaluated=2, n_match=2, n_missing_operand=0, verdict=HOLDS` | `n_in_subset=2, n_evaluated=1, n_match=1, n_missing_operand=1, verdict=PARTIAL (1 rows excluded: required operand missing)` |
| **all `Total All` missing** (`test_missing_as_zero_all_total_all_missing_no_typeerror`) | `TypeError` converting `<NA>` min to float | `n_evaluated=0, n_excluded_missing=2, diff_min=<NA>, verdict=PARTIAL …`; no error |
| **missing `Total`** — completed row, `Total = <NA>`, `Total All`, `unknown` present (`test_missing_total_is_not_zero_filled`) | `Total` silently zero-filled → identity "holds" | `n_evaluated=0, verdict=PARTIAL …` (`Total` not zero-filled) |
| **aggregate missing vs numeric detail** — C_999 `Total All = <NA>` opposite a detail sum of 9 (`test_aggregate_missing_vs_numeric_detail_not_acceptable`) | `reconciles_numeric=True` used as acceptance | `cmp_other_missing ≥ 1`, `acceptable=False`, `reconciles_missing_as_zero=False` |
| authorised blank `unknown` (`test_authorised_blank_unknown_still_holds`) | — | `n_convention_rows=1, n_match=1, verdict=HOLDS (missing-as-zero convention)` |
| ordinary valid completed rows (`test_ordinary_valid_reconciliation`) | — | all `expected` checks `HOLDS` |
| broken incomplete row `bandsum 2` vs `Total All 9` (`test_reconciliation_fails_on_broken_row`) | — | `verdict=FAILS, n_mismatch=1, n_match=1, diff_min=-7` |

## F. Complete 105-band schema validation results

`test_band_schema_accepts_exact_105`: a header with the canonical 105 bands →
`validate_extract(...)["ok"] is True`, `expected_band_schema_ok is True`,
`load_rtt_csv` succeeds.

`test_band_schema_rejects_malformed` (parametrized) — each returns `ok=False`,
`expected_band_schema_ok=False`, a matching problem string, and `load_rtt_csv`
raises `ValueError`:

| Mutation | Problem reported |
|---|---|
| drop all 105 bands | `expected 105 week-band columns, found 0` |
| keep a single 5–6 week band | `… found 1` |
| drop the first (`0-1`) band | `missing expected week-band column(s): Gt 00 To 01 Weeks SUM 1 …` |
| drop the open-ended (`>104`) band | `missing expected week-band column(s): Gt 104 Weeks SUM 1` |
| drop an interior band | `missing expected week-band column(s): …` (also caught pre-fix by contiguity) |
| duplicate a band | `duplicate week-band column(s): …` |
| add an unexpected band (`Gt 200 To 201 …`) | `unexpected week-band-like column(s): Gt 200 To 201 Weeks SUM 1` |

The real June extract passes (`expected_band_schema_ok=True`, 105 bands, ordered).

## G. Documentation synchronization results

Searched **active** project docs (excluding the two audit reports and the
banner-superseded `phase2_completion_report.md`, which are historical evidence)
for: `blank ≡ 0`; "23 detail rows" / C_999 exact-equality-on-every-column;
May 65.6% used to validate June; June publication unavailable; missing-as-zero
described as universal semantics.

| Pattern | Found (active) | Action |
|---|---|---|
| `blank ≡ 0` (semantic) | `docs/data_dictionary.md` week-band row | **Replaced** with the scoped numerical convention + "blank stays `<NA>`" wording. |
| C_999 "exact sum of the 23 detail rows on every numeric column, for all 40,636 groups" | `docs/data_dictionary.md` C_999 bullet | **Replaced** with 1–23 available-rows / 18-of-40,636 / missingness-states wording. |
| May 65.6% recommended as a June comparison; "June … not available at Phase 2 time" | `docs/assumptions.md` "Recommended next validation step" | **Replaced** with the same-month June benchmark table + P2-U1 scoped to the estimate-inclusive uplift. |
| missing-as-zero = universal semantics | none | — (D-016 / `rtt_semantics.md` §5 already scoped) |
| remaining `blank ≡ 0` strings | `docs/decisions.md` D-016 / D-030 | **Left** — they *record the removal* of that wording, not an assertion. |

`docs/phase2_independent_audit.md`, `docs/phase2_closure_audit.md` and the
superseded `docs/phase2_completion_report.md` (which already carries a
"SUPERSEDED IN PART" banner naming these items) were **not** edited — they
accurately document historical findings.

## H. Previously closed findings — intact

No change to the code, outputs, tests or wording for **P2-A02** (completed
unknown-clock blanks 6,032 / 11,005; strict subsets), **P2-A03** (per-part NONC
counts 1,224 / 4,478 / 31,156 / 7,734 / 6,649; prevalence vs checksum),
**P2-A05** (`RTG`/`84H` `Part_2A > Part_2` preserved & flagged), **P2-A07**
(`dropna=False` + count conservation; narrowed disjointness), **P2-A10**
(curated controlled examples). The June regression tests for all five still
pass unchanged. K-1 and K-2 policies are unchanged. No correct June numerical
result was altered.

Where an existing test changed: the synthetic `TestCodeCorrectness` tests now
load via `_load(...)` (`require_full_band_schema=False`) because the production
gate — correctly — rejects a 4-band miniature CSV; the *behaviour under test*
in each is unchanged. `test_reconciliation_*` assertions were updated for the
new field names (`n_convention_rows`) and the corrected verdict text
(`PARTIAL (N rows excluded: required operand missing)`), reflecting the P2-R01
fix rather than a change in June results.

## I. Raw hash / notebook / reproducibility results

| Check | Result |
|---|---|
| `pytest -q` | 98 passed, 0 failed, 0 skipped |
| Phase 1 notebook | 0 errors |
| Phase 2 notebook | 0 errors |
| June raw SHA-256 | `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02` (unchanged, matches required) |
| April / May raw SHA-256 | `0486aca5…56e9` / `fee364bc…5707` (unchanged; not parsed) |
| Phase 2 outputs | regenerated; `c999_acceptable=True`, `extract_validation.ok=True`, `expected_band_schema_ok=True`, `candidate_key_usable=True` |
| Phase 3 | not begun — no band reshaping, SQL/BI model, DuckDB, Parquet, Spark, ML |

## J. Recommendation

**READY FOR FINAL CODEX CLOSURE CHECK.**

All five residual blockers are addressed with focused code + regressions and the
three active-documentation contradictions are synchronised: P2-R01's
missing-as-zero path can no longer certify an undefined comparison (both-operand
requirement, explicit-equality match count, `PARTIAL` for missing required
operands, policy-aware `acceptable` for aggregates); the extract gate enforces
the exact 105-band schema; the data dictionary and assumptions passages now
match the accepted conclusions. The reproduced June figures are unchanged and
the five previously-closed findings and K-1/K-2 are intact. Six items remain
explicitly UNRESOLVED (P2-U1…U7) and are appropriately bounded for later work.

This is Claude's recommendation only. Phase 2 is not declared PASS here, and
Phase 3 is not begun.
