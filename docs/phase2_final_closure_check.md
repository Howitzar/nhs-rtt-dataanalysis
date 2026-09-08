# Final Phase 2 closure check

7 September 2026. Scope: P2-A01, P2-A04/P2-R01, P2-A06, P2-A08 and P2-A09 only, with a targeted regression check of previously closed findings. **Final verdict: PASS.**

## A. Reproducibility results

All Python execution used `C:\Users\abdul\venvs\nhs-rtt\Scripts\python.exe`. The attached second remediation report was treated as claims; current source, tests, documentation, executed results and independent counterexamples supplied the evidence. It is byte-identical to `docs/phase2_closure_remediation_report.md` (SHA-256 `f1e3beffb7a31fd23323aff93e92c555c918334dc14cf62f8bf996576aafd291`).

| Check | Result |
|---|---|
| Full `python -m pytest -q` | **98 passed in 11.00 seconds**, 0 failed, 0 skipped |
| Reported count | Accurate: 47 Phase 1 + 51 Phase 2; Phase 2 class split 39 correctness cases, 2 immutability, 10 June invariants |
| `01_data_discovery.ipynb` | **0 errors**, 8 original code cells executed, **21.4665 seconds** |
| `02_semantics_grain_validation.ipynb` | **0 errors**, 11 original code cells executed, **16.1825 seconds** |
| Regenerated Phase 1 outputs | All **9 CSVs** byte-identical to current saved outputs |
| Regenerated Phase 2 outputs | All **10 CSV/JSON files** byte-identical to current saved outputs |
| Original notebooks | Bytes unchanged by this check |
| Raw files | All three hashes unchanged before/after execution and matching the previous closure's hashes |
| Phase 3 | No new Phase 3 processing found in the reviewed implementation, notebook, tests or scope inventory |

Notebook execution used separate audit copies: only output paths were redirected, plus one interpreter-identification cell added to each. Including that audit cell, executed counts are 9 and 12. The production notebooks and outputs were not overwritten. Runtime warnings about the Windows ZeroMQ selector fallback and local kernel transport did not cause errors; no Windows configuration was altered. Initial sandbox process denials for the new audit scripts were resolved through approved escalation.

Raw SHA-256 values:

- June: `edc3927e4a0065855ad3b2347e7f82688e687b065406eefb49e2f67a9cd67f02` — matches the required value.
- April: `0486aca5891a96af4f15e2f4559795138baef08b0ed580602b8c3a7aec6a56e9`.
- May: `fee364bc3654cf666f79d3485d26e2ada649a3418988a47aa1784e93294a5707`.

April and May were hashed only, not parsed or analyzed. Phase 1 source/tests and dependency files show no unstaged differences against the index. No new band reshaping, Parquet/DuckDB/SQL/BI or other Phase 3 implementation was found. This is a focused check, not a historical attestation of every repository edit.

## B. Residual closure table

| Residual | Status | Independently verified closure evidence |
|---|---|---|
| **P2-A01** | **CLOSED** | The active dictionary's band row explicitly preserves missingness, permits zero contribution only for validated June calculations, distinguishes arithmetic compatibility from semantic equivalence, and disallows automatic transfer to another file. It now agrees with D-016. |
| **P2-A04 / P2-R01** | **CLOSED** | All six requested counterexamples behave correctly. Both operands must remain nonmissing after authorized contributions; missing required operands are excluded and counted, matches come from actual equalities, and zero evaluated rows return missing extrema without errors. Aggregate missing versus numeric detail yields `acceptable=False`; code explicitly requires `cmp_other_missing == 0` for overall acceptance. |
| **P2-A06** | **CLOSED** | The final assumptions passage now states that June's publication is available, records reproduced unestimated counts and the rate at publication precision, and defers only the estimate-inclusive uplift. The May comparison survives only as explicitly withdrawn history. |
| **P2-A08** | **CLOSED** | The dictionary now describes 1–23 available detail rows, only 18 groups with all 23, separate missingness states, and zero mismatches where both sides are numeric. It distinguishes convention-based reconciliation from observed equality and retains C_999 OR detail, never both. |
| **P2-A09** | **CLOSED** | Default `validate_extract` and `load_rtt_csv` accept the independently constructed exact 105-band schema and reject all seven requested malformed variants. Reordered bands are also rejected. This is a small Phase 2 extract contract, with generic Phase 1 discovery left separate. |

### Independent reconciliation counterexamples

The audit used independently constructed nullable-integer frames with ordinary positive counts: observed bands sum to 5, Total=5, unknown=2, Total All=7 before each specified mutation. It did not call repository test fixtures. Counts below apply to the affected identity, not unrelated checks whose operands are still present.

| Case | Evaluated | Missing/excluded | Matches | Result |
|---|---:|---:|---:|---|
| One valid row + one missing Total All | 1 of 2 | 1 | 1 | PARTIAL for both convention identities |
| All Total All missing | 0 of 2 | 2 | 0 | PARTIAL; missing min/max; no error |
| Missing Total | 0 of 1 | 1 | 0 | PARTIAL for `Total + unknown(→0) = Total All` |
| Entire band distribution missing | 0 of 1 | 1 | 0 | PARTIAL for `observed_bandsum + unknown(→0) = Total All`; observed sum stays missing |
| Authorized blank unknown, Total All=5 | 1 of 1 | 0 | 1 | HOLDS with convention label; `n_convention_rows=1` |
| Ordinary valid row | 1 of 1 | 0 | 1 | HOLDS; no convention needed |

For missing Total, the separate band-based identity can legitimately hold because it does not use Total. For an all-missing distribution, the separate Total-based identity can legitimately hold because its operands remain populated. Neither is a false certification of the identity with the missing operand.

Every tested result satisfies `n_match + n_mismatch = n_evaluated` and `n_evaluated + n_excluded_missing = n_in_subset`. The tested frames remain unchanged. Missing Total and Total All are no longer filled; entirely missing bands stay missing. The only explicit completed-path fill is the authorized unknown-clock contribution.

Aggregate probes also tested missing aggregate against positive detail, missing aggregate against zero detail, and positive aggregate against missing detail: each produces `cmp_other_missing=1` and **`acceptable=False`**. Numeric equality is accepted; numeric inequality is rejected. Both-missing and aggregate-zero/all-missing-detail states remain separately counted and accepted under the stated convention. `reconciles_numeric` remains a documented diagnostic, not overall acceptance. Orphan/duplicate rejection is preserved in source and passing regression tests.

### Independent default-schema counterexamples

The expected sequence was built independently in the audit script, without calling `expected_week_band_names()` or importing test fixtures.

| Input | Validator | Default loader |
|---|---|---|
| Exact 105 bands: 0–1 through 103–104, then 104+ | Accept | Accept |
| Zero bands | Reject | ValueError |
| Single 5–6 band | Reject | ValueError |
| Missing first band | Reject | ValueError |
| Missing final/open-ended band | Reject | ValueError |
| Missing interior band | Reject | ValueError |
| Duplicate band | Reject | ValueError |
| Unexpected extra 200–201 band | Reject | ValueError |
| First two bands reordered | Reject | ValueError |

Production defaults retain full validation. Explicitly bypassing the full-band contract in miniature non-schema unit tests is appropriate; those fixtures do not purport to be valid production extracts. June is tested and executed through the default full-schema boundary.

### Previously closed findings: regression check only

**P2-A02, P2-A03, P2-A05, P2-A07 and P2-A10 remain closed.** The existing June assertions pass, and the following saved tables are byte-identical to the prior closure evidence: blank/zero counts, reconciliation subset coverage, per-part NONC counts, subset violations, controlled examples and same-month totals. This corroborates preservation of the completed unknown-clock counts, NONC separation, RTG/84H exception and curated examples without redoing their raw-data audit. Grain guidance still uses `dropna=False`, count conservation, one part/one TFC representation and qualified disjointness statements.

The test count is accurate. The correctness class still contains a June-backed controlled-example test, so class counts should not be read as counts of exclusively synthetic evidence. This does not affect closure. The additional regressions address actual prior defects; independent probes specifically add coverage of the entirely missing distribution case required in this final brief.

## C. Any new blocking defect

**None identified in this focused review.** No new HIGH/CRITICAL defect was established, and no material regression of the previously closed findings was found.

K-1 and K-2 remain approved under their previously accepted scopes. Estimate-inclusive uplift, cross-month validation/revisions, provider classification, and the flagged RTG/84H source exception retain their documented later-phase restrictions. They do not prevent Phase 2 closure and are not silently declared resolved by this verdict.

## D. Final Phase 2 verdict

**PASS**

All five residual blockers, including P2-R01, are closed. Phase 2 can now be marked complete and provides a defensible foundation for Phase 3 under its documented acceptance conditions and unresolved-item restrictions.

No implementation fixes were made. Only this final report and evidence under `outputs/audit/phase2_final/` were added: counterexample script/fixtures/results, a notebook execution helper, a workspace-local kernel specification, executed notebook copies, raw hashes and redirected outputs. Existing source, tests, raw files, notebooks and production outputs were not changed by this check. **Phase 3 was not begun.**
